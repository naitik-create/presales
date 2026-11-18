"""Import every module that registers job handlers, so the worker knows them all."""
import app.models  # noqa: F401
import app.modules.demo.service  # noqa: F401
import app.modules.knowledge.service  # noqa: F401
import app.modules.rfp.routes  # noqa: F401  (rfp.proposal)
import app.modules.rfp.service  # noqa: F401
