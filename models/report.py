from odoo import models, fields, api
from odoo.tools.safe_eval import safe_eval
from odoo.exceptions import UserError
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

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
            # If user manually edited description, we might want to keep it?
            # But compute with store=True usually overwrites unless we check context or something.
            # For simplicity, let's auto-generate. If user wants custom, they can edit, but it might be overwritten on change.
            # To allow manual override that persists, we'd need a flag or check if value matches auto-generated.
            # Let's just auto-generate for now as requested "thêm cho t mô tả phù hợp với code".
            
            def label(field):
                if not field:
                    return ''
                f = self.env['ir.model.fields'].sudo().search([('model', '=', 'crm.lead'), ('name', '=', field)], limit=1)
                return (f.field_description if f and f.field_description else field)
            
            time_label = dict(self._fields['time_filter'].selection).get(rec.time_filter, 'thời gian')
            group_label = label(rec.group_field)
            value_label = label(rec.value_field) if rec.value_field else 'Số lượng'
            
            desc = ""
            if rec.chart_type == 'pie':
                desc = f"Biểu đồ tròn thể hiện tỷ lệ phân bố {value_label} theo {group_label}."
            elif rec.chart_type == 'bar':
                desc = f"Biểu đồ cột so sánh {value_label} giữa các {group_label}."
            elif rec.chart_type == 'line':
                desc = f"Biểu đồ đường thể hiện xu hướng biến động của {value_label} theo {time_label}."
            
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

        try:
            if self.group_field:
                try:
                    groups = Model.read_group(domain, [self.group_field], [self.group_field], lazy=False)
                except Exception:
                    _logger.exception('read_group(groups) failed for report %s', self.id)
                    groups = []

                sum_map = {}
                if self.value_field:
                    try:
                        grp_sum = Model.read_group(domain, [self.group_field, self.value_field], [self.group_field], lazy=False)
                    except Exception:
                        _logger.exception('read_group(sum) failed for report %s', self.id)
                        grp_sum = []
                    for g in grp_sum:
                        key = g.get(self.group_field)
                        gid = key[0] if isinstance(key, (list, tuple)) else key
                        sum_map[gid] = g.get(self.value_field) or 0.0

                group_entries = []
                for g in groups:
                    key = g.get(self.group_field)
                    gid = key[0] if isinstance(key, (list, tuple)) else key
                    lbl = key[1] if isinstance(key, (list, tuple)) and len(key) > 1 else (key or 'Undefined')
                    cnt = g.get('__count', 0)
                    sval = sum_map.get(gid, cnt if not self.value_field else 0.0)
                    group_entries.append({'gid': gid, 'label': str(lbl), 'count': cnt, 'sum': float(sval)})

                limit_n = int(self.limit) if getattr(self, 'limit', 0) and int(self.limit) > 0 else 0
                if limit_n and len(group_entries) > limit_n:
                    sort_key = 'sum' if self.value_field else 'count'
                    group_entries = sorted(group_entries, key=lambda x: x[sort_key], reverse=True)[:limit_n]

                for entry in group_entries:
                    labels.append(entry['label'])
                    count_values.append(entry['count'])
                    sum_values.append(entry['sum'])
            else:
                total = Model.search_count(domain)
                labels = ['All']
                count_values = [total]
                if self.value_field:
                    rows = Model.read_group(domain, [self.value_field], [], lazy=False)
                    total_sum = rows[0].get(self.value_field) if rows else 0.0
                    sum_values = [total_sum or 0.0]
                else:
                    sum_values = [total]

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


