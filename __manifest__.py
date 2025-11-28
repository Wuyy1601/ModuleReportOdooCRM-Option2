{
    'name': 'Looker Studio Reports',
    'version': '4.0.0',
    'summary': 'Advanced CRM Analytics & Reporting Dashboard',
    'description': '''
        Comprehensive CRM reporting module with:
        - Main Chart (based on Group By Field)
        - Detailed Data Table
        - KPIs (Leads, Opportunities, Customers, Revenue, Deal Size, Rates)
        - Customer by Level Analysis (Pie Chart)
        - Lost Reason Analysis (Pie Chart)
        - Pipeline Value by Stage
        - Win/Loss Trend over Time
        - Sales Performance Report by Salesperson (Group By All/Specific)
    ''',
    'category': 'Reporting',
    'author': 'Your Name',
    'depends': ['base', 'web', 'website', 'crm', 'sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/report_views.xml',
        'views/website_templates.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'looker_studio/static/src/js/patch_removefacet.js',
        ],
        'web.assets_web': [
            'looker_studio/static/src/js/patch_removefacet.js',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
