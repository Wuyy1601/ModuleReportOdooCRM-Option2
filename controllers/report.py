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
        
        # Get Data (time filter is handled in model)
        kpi_data = report.get_kpi_data()
        chart_data = report.get_chart_data()
        detail_data = report.get_detail_data()

        context = {
            'report': report,
            'kpi': kpi_data,
            'detail_data': detail_data,
            'labels_json': json.dumps(chart_data.get('labels', [])),
            'counts_json': json.dumps(chart_data.get('count_values', [])),
            'sums_json': json.dumps(chart_data.get('sum_values', [])),
            'line_labels_json': json.dumps(chart_data.get('line_labels', [])),
            'line_values_json': json.dumps(chart_data.get('line_values', [])),
            'json': json,
        }
        return request.render('looker_studio.report_kpi_template_v2', context)

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