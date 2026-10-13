from streamlit.testing.v1 import AppTest
from pathlib import Path

def test_all_dashboard_pages_render():
    for page in ["Executive Overview", "Revenue & Sales", "Customer Support", "Delivery & Capacity", "Management Issues", "AI Chief of Staff", "Action Center", "Workflow Monitor", "Data Management"]:
        app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
        assert not app.exception
        section = next(name for name, routes in {
            'Overview':['Executive Overview'],
            'Business Performance':['Revenue & Sales','Customer Support','Delivery & Capacity'],
            'Decision Intelligence':['Management Issues','AI Chief of Staff','Action Center','Workflow Monitor'],
            'Administration':['Data Management'],
        }.items() if page in routes)
        app.radio(key='nav_'+section).set_value(page).run(timeout=30)
        assert not app.exception
