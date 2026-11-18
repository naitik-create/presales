from fastapi import FastAPI


def register_routers(app: FastAPI) -> None:
    from app.modules.admin.routes import router as admin
    from app.modules.ask.routes import router as ask
    from app.modules.auth.routes import router as auth
    from app.modules.branding.routes import admin as branding_admin
    from app.modules.branding.routes import public as branding
    from app.modules.customers.routes import router as customers
    from app.modules.dashboard.routes import router as dashboard
    from app.modules.demo.routes import router as demo
    from app.modules.knowledge.routes import router as knowledge
    from app.modules.rfp.routes import router as rfp
    from app.modules.scorecard.routes import router as scorecard
    from app.modules.search.routes import router as search

    for r in (auth, branding, branding_admin, admin, knowledge, ask, customers, rfp, demo, scorecard, search, dashboard):
        app.include_router(r, prefix="/api")
