from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict

_logger = logging.getLogger(__name__)


class LookerReport(models.Model):
    """Simple report record used by the Looker Studio module.

    The model always targets `crm.lead` as data source. This file focuses on
    generating chart-friendly aggregates and on small helpers that auto-fill
    user-facing descriptions in Vietnamese when they are not provided.
    """

    _name = 'looker_studio.report'
    _description = 'Looker Studio - Report (simple)'

    name = fields.Char(required=True)
    # Always use crm.lead as data source
    domain = fields.Text(string='Domain', help='Python literal list domain, e.g. [("stage_id","=","won")]')
    group_field = fields.Selection(selection='_get_crm_group_fields', string='Group By Field', help='CRM field to group by')
    value_field = fields.Selection(selection='_get_crm_value_fields', string='Value Field', help='Numeric CRM field to aggregate (sum)')
    chart_type = fields.Selection([('bar', 'Bar'), ('line', 'Line'), ('pie', 'Pie')], default='bar')
    limit = fields.Integer(string='Limit', default=1000)
    
    time_filter = fields.Selection([
        ('last_3_months', '3 tháng gần nhất'),
        ('last_6_months', '6 tháng gần nhất'),
        ('this_year', 'Năm nay'),
        ('custom', 'Tùy chọn'),
    ], string='Time Filter', default='this_year')
    
    date_from = fields.Date(string='Từ ngày')
    date_to = fields.Date(string='Đến ngày')

    description = fields.Text(string='Description', compute='_compute_description', store=True, readonly=False)
    
    # Deprecated fields - kept for migration safety but not used
    pie_description = fields.Text(string='Pie description')
    line_description = fields.Text(string='Line description')
    bar_description = fields.Text(string='Bar description')
    
    success_domain = fields.Text(string='Success Domain', help='Domain (Python list) selecting records considered "success" for percentage calculation, e.g. [("stage_id","=","won")]')

    @api.depends('group_field', 'value_field', 'domain', 'time_filter', 'chart_type')
    def _compute_description(self):
        for rec in self:
            def label(field):
                if not field:
                    return ''
                f = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead'), ('name', '=', field)], limit=1)
                return (f.field_description if f and f.field_description else field)
            
            time_label = dict(self._fields['time_filter'].selection).get(rec.time_filter, 'thời gian')
            # Default to stage_id if no group_field
            group_label = label(rec.group_field) if rec.group_field else 'Giai đoạn'
            # Default to expected_revenue if no value_field  
            value_label = label(rec.value_field) if rec.value_field else 'Doanh thu dự kiến'
            
            desc = ""
            if rec.chart_type == 'pie':
                desc = f"Biểu đồ tròn thể hiện tỷ lệ phân bố {value_label} theo {group_label}."
            elif rec.chart_type == 'bar':
                desc = f"Biểu đồ cột so sánh {value_label} giữa các {group_label}."
            elif rec.chart_type == 'line':
                desc = f"Biểu đồ đường thể hiện xu hướng biến động của {value_label} theo {time_label}."
            else:
                desc = f"Phân tích {value_label} theo {group_label} trong {time_label}."
            
            if rec.domain:
                desc += " (Dữ liệu đã được lọc)."
                
            rec.description = desc

    # --- Auto-generation helpers for description fields ---
    def _crm_field_label(self, field_name):
        """Return the human label for a CRM field or the raw name as fallback."""
        if not field_name:
            return ''
        f = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead'), ('name', '=', field_name)], limit=1)
        return (f.field_description if f and f.field_description else field_name)

    def _build_pie_description(self):
        return ('Phân bố khách hàng tiềm năng theo %s.' % self._crm_field_label(self.group_field)) if self.group_field else 'Phân bố khách hàng tiềm năng.'

    def _build_bar_description(self):
        if self.group_field and self.value_field:
            return 'Tổng %s theo %s.' % (self._crm_field_label(self.value_field), self._crm_field_label(self.group_field))
        if self.group_field:
            return 'Số lượng khách hàng tiềm năng theo %s.' % (self._crm_field_label(self.group_field),)
        return 'Giá trị theo danh mục.'

    def _build_line_description(self):
        domain_part = ' (có áp dụng bộ lọc)' if self.domain else ''
        time_label = dict(self._fields['time_filter'].selection).get(self.time_filter, 'thời gian')
        # If a success_domain is set, show success percentage trend
        if self.success_domain:
            return 'Xu hướng tỷ lệ phần trăm khách hàng tiềm năng theo %s%s.' % (time_label, domain_part)
        if self.value_field:
            return 'Xu hướng tổng %s theo %s%s.' % (self._crm_field_label(self.value_field), time_label, domain_part)
        return 'Xu hướng số lượng khách hàng tiềm năng theo %s%s.' % (time_label, domain_part)

    def _eval_domain(self):
        if not self.domain:
            return []
        try:
            return safe_eval(self.domain)
        except Exception:
            return []

    @api.model
    def _get_crm_group_fields(self):
        """Return a selection of sensible group-by fields for crm.lead."""
        allowed = ['stage_id', 'user_id', 'team_id', 'partner_id', 'company_id', 'country_id']
        res = []
        for name in allowed:
            f = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead'), ('name', '=', name)], limit=1)
            if f:
                res.append((f.name, f.field_description or f.name))
        if not res:
            fields = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead')])
            for f in fields:
                if f.ttype in ('char', 'selection', 'many2one'):
                    res.append((f.name, f.field_description or f.name))
        return res

    @api.model
    def _get_crm_value_fields(self):
        """Return a selection of numeric fields usable as value metrics."""
        allowed = ['expected_revenue', 'planned_revenue', 'probability']
        res = []
        for name in allowed:
            f = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead'), ('name', '=', name)], limit=1)
            if f and f.ttype in ('integer', 'float', 'monetary'):
                res.append((f.name, f.field_description or f.name))
        if not res:
            fields = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead')])
            for f in fields:
                if f.ttype in ('integer', 'float', 'monetary'):
                    res.append((f.name, f.field_description or f.name))
        return res

    def _get_time_domain(self):
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = datetime.strptime(today, '%Y-%m-%d').date()
        
        start_date = None
        end_date = today
        
        if self.time_filter == 'last_3_months':
            start_date = today - relativedelta(months=3)
        elif self.time_filter == 'last_6_months':
            start_date = today - relativedelta(months=6)
        elif self.time_filter == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        elif self.time_filter == 'custom':
            start_date = self.date_from
            end_date = self.date_to
            
        if start_date and end_date:
            return [('create_date', '>=', start_date), ('create_date', '<=', end_date)]
        return []

    def get_chart_data(self, additional_domain=None):
        """Aggregate data for charts.

        Returns a dict with keys: labels, count_values, sum_values, line_labels, line_values.
        Always returns lists (never None) to simplify template handling.
        If no group_field is set, defaults to grouping by stage_id for standard CRM analysis.
        """
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        labels = []
        count_values = []
        sum_values = []

        # Use group_field if set, otherwise default to stage_id for standard CRM report
        effective_group_field = self.group_field or 'stage_id'

        try:
            try:
                groups = Model.read_group(domain, [effective_group_field], [effective_group_field], lazy=False)
            except Exception:
                _logger.exception('read_group(groups) failed for report %s', self.id)
                groups = []

            sum_map = {}
            # Default to expected_revenue if no value_field set
            effective_value_field = self.value_field or 'expected_revenue'
            try:
                grp_sum = Model.read_group(domain, [effective_group_field, effective_value_field], [effective_group_field], lazy=False)
            except Exception:
                _logger.exception('read_group(sum) failed for report %s', self.id)
                grp_sum = []
            for g in grp_sum:
                key = g.get(effective_group_field)
                gid = key[0] if isinstance(key, (list, tuple)) else key
                sum_map[gid] = g.get(effective_value_field) or 0.0

            group_entries = []
            for g in groups:
                key = g.get(effective_group_field)
                gid = key[0] if isinstance(key, (list, tuple)) else key
                lbl = key[1] if isinstance(key, (list, tuple)) and len(key) > 1 else (key or 'Không xác định')
                cnt = g.get('__count', 0)
                sval = sum_map.get(gid, 0.0)
                group_entries.append({'gid': gid, 'label': str(lbl), 'count': cnt, 'sum': float(sval)})

            limit_n = int(self.limit) if getattr(self, 'limit', 0) and int(self.limit) > 0 else 0
            if limit_n and len(group_entries) > limit_n:
                sort_key = 'sum' if self.value_field else 'count'
                group_entries = sorted(group_entries, key=lambda x: x[sort_key], reverse=True)[:limit_n]

            for entry in group_entries:
                labels.append(entry['label'])
                count_values.append(entry['count'])
                sum_values.append(entry['sum'])

            # Time-series comparison
            # If time_filter is 'this_month', group by day. Else group by month.
            groupby_period = 'create_date:month'
            if self.time_filter == 'this_month':
                groupby_period = 'create_date:day'
            
            try:
                if self.value_field:
                    ts_groups = Model.read_group(domain, ['create_date', self.value_field], [groupby_period], lazy=False)
                else:
                    ts_groups = Model.read_group(domain, ['create_date'], [groupby_period], lazy=False)
            except Exception:
                _logger.exception('read_group(time-series) failed for report %s', self.id)
                ts_groups = []

            line_labels = []
            line_values = []
            
            # Sort groups by date just in case
            # read_group usually returns sorted by group key
            
            for g in ts_groups:
                key = g.get(groupby_period)
                # key is usually a string like "January 2025" or "2025-01-01" depending on locale and version
                # But read_group with date granularity returns formatted string.
                # We can use it directly as label.
                line_labels.append(str(key))
                if self.value_field:
                    line_values.append(g.get(self.value_field) or 0.0)
                else:
                    line_values.append(g.get('__count', 0))

            return {
                'labels': labels,
                'count_values': count_values,
                'sum_values': sum_values,
                'line_labels': line_labels,
                'line_values': line_values,
            }
        except Exception:
            _logger.exception('Unexpected error in get_chart_data for report %s', getattr(self, 'id', '?'))
            return {'labels': [], 'count_values': [], 'sum_values': [], 'line_labels': [], 'line_values': []}

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/looker_studio/report/{self.id}',
            'target': 'new',
        }

    def get_kpi_data(self, additional_domain=None):
        """Calculate specific KPIs for the report."""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        # Base domains
        lead_domain = domain + [('type', '=', 'lead')]
        opp_domain = domain + [('type', '=', 'opportunity')]

        # 1. Number of Leads
        lead_count = Model.search_count(lead_domain)

        # 2. Number of Opportunities
        active_opp_count = Model.search_count(opp_domain)
        
        # Lost opportunities
        lost_domain = domain + [('type', '=', 'opportunity'), ('active', '=', False)]
        lost_count = Model.with_context(active_test=False).search_count(lost_domain)
        
        total_opps = active_opp_count + lost_count

        # 3. Forecast (Expected Revenue of Active Opportunities)
        forecast_data = Model.read_group(opp_domain, ['expected_revenue'], [])
        forecast = forecast_data[0]['expected_revenue'] if forecast_data else 0.0

        # 5. Percentage Won
        won_domain = opp_domain + [('stage_id.is_won', '=', True)]
        won_count = Model.search_count(won_domain)
        won_rate = (won_count / total_opps * 100) if total_opps > 0 else 0.0

        # 6. Percentage Lost
        lost_rate = (lost_count / total_opps * 100) if total_opps > 0 else 0.0

        # 7. Percentage converted from Lead to Opportunity
        # Proxy: Opps / (Leads + Opps)
        total_records = lead_count + total_opps
        conversion_rate = (total_opps / total_records * 100) if total_records > 0 else 0.0

        return {
            'lead_count': lead_count,
            'opp_count': active_opp_count, # Display active opps count usually
            'total_opps': total_opps,      # Internal use or display if needed
            'forecast': forecast,
            'won_rate': round(won_rate, 2),
            'lost_rate': round(lost_rate, 2),
            'conversion_rate': round(conversion_rate, 2),
        }

    def get_detail_data(self, additional_domain=None):
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain
        
        # Fields to fetch
        fields_to_read = ['name', 'partner_id', 'user_id', 'stage_id', 'expected_revenue', 'probability', 'create_date', 'type', 'active', 'lost_reason_id']
        if self.group_field and self.group_field not in fields_to_read:
             # Check if it's a valid field on crm.lead
             if self.group_field in Model._fields:
                 fields_to_read.append(self.group_field)

        limit = self.limit or 100
        # Include lost leads (active=False)
        records = Model.with_context(active_test=False).search_read(domain, fields_to_read, limit=limit, order='create_date desc')
        return records

    def get_funnel_data(self, additional_domain=None):
        """Get data for funnel chart based on actual CRM stages"""
        self.ensure_one()
        Model = self.env['crm.lead']
        Stage = self.env['crm.stage']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        # Get all stages ordered by sequence
        all_stages = Stage.search([], order='sequence asc')
        
        # Count Leads first
        lead_domain = domain + [('type', '=', 'lead')]
        lead_count = Model.search_count(lead_domain)
        
        # Count opportunities by each stage
        opp_domain = domain + [('type', '=', 'opportunity')]
        
        # Build funnel data from stages
        funnel_stages = []
        colors = ['#6c757d', '#17a2b8', '#ffc107', '#fd7e14', '#007bff', '#28a745', '#20c997', '#6610f2']
        
        # Add Leads as first stage
        funnel_stages.append({
            'name': 'Leads',
            'count': lead_count,
            'color': colors[0],
            'revenue': 0
        })
        
        # Add each CRM stage with count and revenue
        total_opp = 0
        for idx, stage in enumerate(all_stages):
            stage_domain = opp_domain + [('stage_id', '=', stage.id)]
            count = Model.search_count(stage_domain)
            
            # Get revenue for this stage
            revenue_data = Model.read_group(stage_domain, ['expected_revenue:sum'], [])
            revenue = revenue_data[0].get('expected_revenue', 0) if revenue_data else 0
            
            total_opp += count
            
            funnel_stages.append({
                'name': stage.name,
                'count': count,
                'color': colors[(idx + 1) % len(colors)],
                'revenue': revenue or 0,
                'is_won': stage.is_won
            })
        
        # Also count lost opportunities
        lost_domain = domain + [('type', '=', 'opportunity'), ('active', '=', False)]
        lost_count = Model.with_context(active_test=False).search_count(lost_domain)
        lost_revenue_data = Model.with_context(active_test=False).read_group(lost_domain, ['expected_revenue:sum'], [])
        lost_revenue = lost_revenue_data[0].get('expected_revenue', 0) if lost_revenue_data else 0
        
        # Get won count
        won_stages = Stage.search([('is_won', '=', True)]).ids
        won_domain = opp_domain + [('stage_id', 'in', won_stages)]
        won_count = Model.search_count(won_domain)
        
        total_opp_all = total_opp + lost_count

        return {
            'stages': funnel_stages,
            'lost': {'count': lost_count, 'revenue': lost_revenue or 0},
            'conversion_rates': {
                'lead_to_opp': round((total_opp_all / lead_count * 100) if lead_count > 0 else 0, 1),
                'opp_to_won': round((won_count / total_opp_all * 100) if total_opp_all > 0 else 0, 1),
                'lead_to_won': round((won_count / lead_count * 100) if lead_count > 0 else 0, 1),
            }
        }

    def get_lost_reason_data(self, additional_domain=None):
        """Get data for Lost Reason Analysis Pie Chart"""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        # Lost opportunities (active=False)
        lost_domain = domain + [('type', '=', 'opportunity'), ('active', '=', False)]
        
        # Group by lost_reason_id
        groups = Model.with_context(active_test=False).read_group(
            lost_domain,
            ['lost_reason_id', 'expected_revenue:sum'],
            ['lost_reason_id'],
            lazy=False
        )

        labels = []
        counts = []
        revenues = []
        colors = [
            '#e74c3c', '#9b59b6', '#3498db', '#1abc9c', '#f39c12',
            '#e67e22', '#95a5a6', '#34495e', '#16a085', '#c0392b'
        ]
        
        total_lost = 0
        for i, g in enumerate(groups):
            reason = g.get('lost_reason_id')
            label = reason[1] if reason else 'Không xác định'
            count = g.get('__count', 0)
            revenue = g.get('expected_revenue', 0) or 0
            
            labels.append(label)
            counts.append(count)
            revenues.append(revenue)
            total_lost += count

        # Calculate percentages
        percentages = [round(c / total_lost * 100, 1) if total_lost > 0 else 0 for c in counts]

        return {
            'labels': labels,
            'counts': counts,
            'revenues': revenues,
            'percentages': percentages,
            'colors': colors[:len(labels)],
            'total_lost': total_lost,
            'total_lost_revenue': sum(revenues),
        }

    def get_pipeline_by_stage_data(self, additional_domain=None):
        """Get pipeline value by stage"""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        opp_domain = domain + [('type', '=', 'opportunity')]
        
        groups = Model.read_group(
            opp_domain,
            ['stage_id', 'expected_revenue:sum'],
            ['stage_id'],
            lazy=False
        )

        labels = []
        counts = []
        revenues = []
        
        for g in groups:
            stage = g.get('stage_id')
            labels.append(stage[1] if stage else 'Undefined')
            counts.append(g.get('__count', 0))
            revenues.append(g.get('expected_revenue', 0) or 0)

        return {
            'labels': labels,
            'counts': counts,
            'revenues': revenues,
            'total_pipeline': sum(revenues),
        }

    def get_win_loss_trend(self, additional_domain=None):
        """Get Win/Loss trend over time"""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        opp_domain = domain + [('type', '=', 'opportunity')]
        
        # Won by month
        won_domain = opp_domain + [('stage_id.is_won', '=', True)]
        won_groups = Model.read_group(
            won_domain,
            ['create_date', 'expected_revenue:sum'],
            ['create_date:month'],
            lazy=False
        )

        # Lost by month  
        lost_domain = domain + [('type', '=', 'opportunity'), ('active', '=', False)]
        lost_groups = Model.with_context(active_test=False).read_group(
            lost_domain,
            ['create_date'],
            ['create_date:month'],
            lazy=False
        )

        # Build timeline data
        won_by_month = {}
        lost_by_month = {}
        
        for g in won_groups:
            month = g.get('create_date:month')
            if month:
                won_by_month[month] = {
                    'count': g.get('__count', 0),
                    'revenue': g.get('expected_revenue', 0) or 0
                }

        for g in lost_groups:
            month = g.get('create_date:month')
            if month:
                lost_by_month[month] = g.get('__count', 0)

        # Merge labels
        all_months = sorted(set(list(won_by_month.keys()) + list(lost_by_month.keys())))
        
        labels = all_months
        won_counts = [won_by_month.get(m, {}).get('count', 0) for m in all_months]
        won_revenues = [won_by_month.get(m, {}).get('revenue', 0) for m in all_months]
        lost_counts = [lost_by_month.get(m, 0) for m in all_months]

        return {
            'labels': labels,
            'won_counts': won_counts,
            'won_revenues': won_revenues,
            'lost_counts': lost_counts,
        }

    def get_source_analysis(self, additional_domain=None):
        """Get revenue by source/campaign"""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        opp_domain = domain + [('type', '=', 'opportunity')]
        
        # By source_id if available
        if 'source_id' in Model._fields:
            groups = Model.read_group(
                opp_domain,
                ['source_id', 'expected_revenue:sum'],
                ['source_id'],
                lazy=False
            )
            
            labels = []
            counts = []
            revenues = []
            
            for g in groups:
                source = g.get('source_id')
                labels.append(source[1] if source else 'Direct/Unknown')
                counts.append(g.get('__count', 0))
                revenues.append(g.get('expected_revenue', 0) or 0)

            return {
                'labels': labels,
                'counts': counts,
                'revenues': revenues,
            }
        
        return {'labels': [], 'counts': [], 'revenues': []}

    def get_deal_metrics(self, additional_domain=None):
        """Get advanced deal metrics"""
        self.ensure_one()
        Model = self.env['crm.lead']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        if additional_domain:
            domain = domain + additional_domain

        opp_domain = domain + [('type', '=', 'opportunity')]
        won_domain = opp_domain + [('stage_id.is_won', '=', True)]
        
        # Average Deal Size
        won_data = Model.read_group(won_domain, ['expected_revenue:avg'], [])
        avg_deal_size = won_data[0].get('expected_revenue', 0) if won_data else 0

        # Total Won Revenue
        total_won_data = Model.read_group(won_domain, ['expected_revenue:sum'], [])
        total_won_revenue = total_won_data[0].get('expected_revenue', 0) if total_won_data else 0

        # Average Probability (Active Opps)
        prob_data = Model.read_group(opp_domain, ['probability:avg'], [])
        avg_probability = prob_data[0].get('probability', 0) if prob_data else 0

        # Count metrics
        total_opps = Model.with_context(active_test=False).search_count(opp_domain)
        active_opps = Model.search_count(opp_domain)
        won_count = Model.search_count(won_domain)

        return {
            'avg_deal_size': round(avg_deal_size, 2),
            'total_won_revenue': round(total_won_revenue, 2),
            'avg_probability': round(avg_probability, 1),
            'total_opps': total_opps,
            'active_opps': active_opps,
            'won_count': won_count,
        }


class LookerActivityReport(models.Model):
    """Report record targeting mail.activity."""

    _name = 'looker_studio.activity_report'
    _description = 'Looker Studio - Activity Report'

    name = fields.Char(required=True)
    domain = fields.Text(string='Domain', help='Python literal list domain')
    group_field = fields.Selection(selection='_get_activity_group_fields', string='Group By Field')
    limit = fields.Integer(string='Limit', default=1000)
    
    time_filter = fields.Selection([
        ('last_3_months', '3 tháng gần nhất'),
        ('last_6_months', '6 tháng gần nhất'),
        ('this_year', 'Năm nay'),
        ('custom', 'Tùy chọn'),
    ], string='Time Filter', default='this_year')
    
    date_from = fields.Date(string='Từ ngày')
    date_to = fields.Date(string='Đến ngày')

    @api.model
    def _get_activity_group_fields(self):
        return [
            ('activity_type_id', 'Activity Type'),
            ('user_id', 'Assigned to'),
            ('create_uid', 'Created by'),
        ]

    def _eval_domain(self):
        if not self.domain:
            return []
        try:
            return safe_eval(self.domain)
        except Exception:
            return []
            
    def _get_time_domain(self):
        today = fields.Date.context_today(self)
        if isinstance(today, str):
            today = datetime.strptime(today, '%Y-%m-%d').date()
        
        start_date = None
        end_date = today
        
        if self.time_filter == 'last_3_months':
            start_date = today - relativedelta(months=3)
        elif self.time_filter == 'last_6_months':
            start_date = today - relativedelta(months=6)
        elif self.time_filter == 'this_year':
            start_date = today.replace(month=1, day=1)
            end_date = today.replace(month=12, day=31)
        elif self.time_filter == 'custom':
            start_date = self.date_from
            end_date = self.date_to
            
        if start_date and end_date:
            # Activities use date_deadline or create_date? Usually date_deadline for planning, create_date for creation.
            # Let's use create_date for "Activity Report" as in "Activities created".
            return [('create_date', '>=', start_date), ('create_date', '<=', end_date)]
        return []

    def get_data(self):
        self.ensure_one()
        Model = self.env['mail.activity']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        
        try:
            # KPIs
            total_activities = Model.search_count(domain)
            
            # Breakdown by Activity Type for cards
            activity_types_data = Model.read_group(domain, ['activity_type_id'], ['activity_type_id'], lazy=False)
            type_counts = []
            for g in activity_types_data:
                if g.get('activity_type_id'):
                    type_counts.append({
                        'name': g['activity_type_id'][1],
                        'count': g['__count']
                    })
                else:
                     type_counts.append({
                        'name': 'Undefined',
                        'count': g['__count']
                    })

            # Grouping
            labels = []
            values = []
            if self.group_field:
                groups = Model.read_group(domain, [self.group_field], [self.group_field], lazy=False)
                for g in groups:
                    key = g.get(self.group_field)
                    lbl = key[1] if isinstance(key, (list, tuple)) and len(key) > 1 else (key or 'Undefined')
                    labels.append(str(lbl))
                    values.append(g.get('__count', 0))
            
            return {
                'total': total_activities,
                'type_counts': type_counts,
                'labels': labels,
                'values': values,
            }
        except Exception as e:
            _logger.error("Error in LookerActivityReport get_data: %s", e)
            return {
                'total': 0,
                'type_counts': [],
                'labels': [],
                'values': [],
                'error': str(e)
            }

    def get_detail_data(self):
        self.ensure_one()
        Model = self.env['mail.activity']
        domain = self._eval_domain()
        time_domain = self._get_time_domain()
        domain = domain + time_domain
        
        try:
            # Fields to fetch
            fields_to_read = ['res_name', 'activity_type_id', 'summary', 'date_deadline', 'user_id', 'state', 'res_model', 'res_id']
            if self.group_field and self.group_field not in fields_to_read:
                 if self.group_field in Model._fields:
                     fields_to_read.append(self.group_field)

            limit = self.limit or 100
            records = Model.search_read(domain, fields_to_read, limit=limit, order='date_deadline asc')

            # Enrich with Salesperson for CRM Leads
            lead_ids = [r['res_id'] for r in records if r.get('res_model') == 'crm.lead']
            if lead_ids:
                leads = self.env['crm.lead'].browse(lead_ids)
                lead_map = {l.id: l.user_id.name for l in leads}
                for r in records:
                    if r.get('res_model') == 'crm.lead':
                        r['salesperson'] = lead_map.get(r['res_id'])

            return records
        except Exception as e:
            _logger.error("Error in LookerActivityReport get_detail_data: %s", e)
            return []

    def action_preview(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/looker_studio/activity_report/{self.id}',
            'target': 'new',
        }


