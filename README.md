# Python App

## Run and debug

From the project root, run `uv run fastapi dev`. The FastAPI entrypoint is
`src.my_first_app.main:app`. In VS Code, select the project Python environment
and use the **FastAPI: debug** launch configuration.

## Application layout

- `src/my_first_app/main.py` creates the app and registers middleware,
  exception handlers, startup, and routers in their existing order.
- `database.py` provides the SQLModel engine and session dependency;
  `exceptions.py` contains the exception handlers.
- `routers/heroes.py`, `auth.py`, `item_examples.py`, `streaming.py`,
  `forms_uploads.py`, and `examples.py` contain feature-specific examples.
  The existing users, items, WebSocket, invoice, and admin routers remain
  separate.
- Some features have multiple router objects so their routes can retain their
  original registration order. The existing session and token dependencies
  remain accessible from `my_first_app.main` for overrides.

## Existing example conflicts

These are preserved intentionally; resolving them would change the API:

| Routes | Current behavior and possible follow-up |
| --- | --- |
| `GET /` | The JSON greeting wins; OpenAPI describes the later upload form. Give the form a distinct path or choose one root. |
| `POST /token` | JWT login wins; OpenAPI describes the later fake-token login. Choose one flow or move the example. |
| `POST /uploadfile/` | The multiple-file handler wins; OpenAPI describes the later handler with different fields. Give them distinct paths or agree on one contract. |
| Item routes | The existing items router wins for overlapping routes, including `/items/stream` and `/items/stream-retry`. Choose a canonical item API and place static paths before parameterized paths. |
| `GET /users/` | The existing users router wins, while OpenAPI describes the later example. Choose one contract or give the example a distinct path. |

The fake password helpers intentionally represent different examples and are not
interchangeable. The existing `/items/stream` implementation and startup
deprecation are also unchanged.