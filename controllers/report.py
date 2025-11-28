from odoo import http
from odoo.http import request
from odoo.tools.safe_eval import safe_eval
import json


class LookerReportController(http.Controller):
    @http.route('/looker_studio/report/<int:report_id>', type='http', auth='user', website=True)
    def render_report(self, report_id, **kwargs):
        report = request.env['looker_studio.report'].sudo().browse(report_id)
        if not report.exists():
            return request.not_found()
        
        # Get Group By Field Label (default to Stage if not set)
        effective_group_field = report.group_field or 'stage_id'
        group_field_label = 'Giai đoạn'  # Default label for stage_id
        
        field_info = request.env['ir.model.fields'].sudo().search([
            ('model', '=', 'crm.lead'),
            ('name', '=', effective_group_field)
        ], limit=1)
        if field_info:
            group_field_label = field_info.field_description or effective_group_field
        
        # Get Data (time filter is handled in model)
        kpi_data = report.get_kpi_data()
        chart_data = report.get_chart_data()
        detail_data = report.get_detail_data()
        
        # New advanced data
        lost_reason_data = report.get_lost_reason_data()
        pipeline_data = report.get_pipeline_by_stage_data()
        win_loss_trend = report.get_win_loss_trend()
        source_data = report.get_source_analysis()
        deal_metrics = report.get_deal_metrics()
        customer_data = report.get_customer_data()

        context = {
            'report': report,
            'group_field_label': group_field_label,
            'kpi': kpi_data,
            'detail_data': detail_data,
            'labels_json': json.dumps(chart_data.get('labels', [])),
            'counts_json': json.dumps(chart_data.get('count_values', [])),
            'sums_json': json.dumps(chart_data.get('sum_values', [])),
            'line_labels_json': json.dumps(chart_data.get('line_labels', [])),
            'line_values_json': json.dumps(chart_data.get('line_values', [])),
            # Lost Reason data
            'lost_reason_data': lost_reason_data,
            'lost_labels_json': json.dumps(lost_reason_data.get('labels', [])),
            'lost_counts_json': json.dumps(lost_reason_data.get('counts', [])),
            'lost_colors_json': json.dumps(lost_reason_data.get('colors', [])),
            # Pipeline data
            'pipeline_data': pipeline_data,
            'pipeline_labels_json': json.dumps(pipeline_data.get('labels', [])),
            'pipeline_revenues_json': json.dumps(pipeline_data.get('revenues', [])),
            # Win/Loss trend
            'trend_data': win_loss_trend,
            'trend_labels_json': json.dumps(win_loss_trend.get('labels', [])),
            'trend_won_json': json.dumps(win_loss_trend.get('won_counts', [])),
            'trend_lost_json': json.dumps(win_loss_trend.get('lost_counts', [])),
            # Source data
            'source_data': source_data,
            'source_labels_json': json.dumps(source_data.get('labels', [])),
            'source_revenues_json': json.dumps(source_data.get('revenues', [])),
            # Deal metrics
            'deal_metrics': deal_metrics,
            # Customer data
            'customer_data': customer_data,
            'customer_labels_json': json.dumps(customer_data.get('labels', [])),
            'customer_counts_json': json.dumps(customer_data.get('counts', [])),
            'customer_colors_json': json.dumps(customer_data.get('colors', [])),
            'json': json,
        }
        return request.render('looker_studio.report_kpi_template_v3', context)

    @http.route('/looker_studio/activity_report/<int:report_id>', type='http', auth='user', website=True)
    def render_activity_report(self, report_id, **kwargs):
        report = request.env['looker_studio.activity_report'].sudo().browse(report_id)
        if not report.exists():
            return request.not_found()
        
        data = report.get_data()
        detail_data = report.get_detail_data()
        
        context = {
            'report': report,
            'total': data.get('total', 0),
            'type_counts': data.get('type_counts', []),
            'detail_data': detail_data,
            'labels_json': json.dumps(data.get('labels', [])),
            'values_json': json.dumps(data.get('values', [])),
            'json': json,
        }
        return request.render('looker_studio.report_activity_template', context)