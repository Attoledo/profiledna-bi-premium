from __future__ import annotations

# Este pacote existe para registrar models no metadata via import (Alembic env.py).
# O Base oficial do projeto é backend.database.Base (SSOT do projeto atual).

import backend.models.admin_user  # noqa: F401
import backend.models.attempt     # noqa: F401
import backend.models.cliente     # noqa: F401
import backend.models.result      # noqa: F401
import backend.models.invite      # noqa: F401
