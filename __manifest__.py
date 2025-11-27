{
    'name': 'Looker Studio Reports',
    'version': '3.2.0',
    'summary': 'Advanced CRM Analytics & Reporting Dashboard',
    'description': '''
        Comprehensive CRM reporting module with:
        - Sales Funnel Visualization (Lead → Opportunity → Won)
        - Lost Reason Analysis (Pie Chart)
        - Pipeline Value by Stage
        - Win/Loss Trend over Time
        - Top Salesperson Performance & Leaderboard
        - Average Deal Size & Sales Cycle Metrics
        - Revenue by Source Analysis
        - Detailed Data Tables with Filtering
    ''',
    'category': 'Reporting',
    'author': 'Your Name',
    'depends': ['base', 'web', 'website', 'crm'],
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
