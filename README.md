# DB Substations - Flask API Deployment

Flask REST API server for DB Substations management system.

## Deployment on Railway

This API is ready to deploy on Railway.app.

### Required Environment Variables

Set these in Railway dashboard:

```
FLASK_ENV=production
DATABASE_PATH=/app/data/database.db
```

### Endpoints

- `GET /api/health` - Health check
- `GET /api/substations` - List substations
- `POST /api/substations` - Add substation
- `PUT /api/substations/<id>` - Update substation
- `DELETE /api/substations/<id>` - Delete substation
- `GET /api/elements` - List elements
- `POST /api/elements` - Add element
- `DELETE /api/elements/<id>` - Delete element

### Local Development

```bash
pip install -r requirements.txt
python api_server.py
```

Server runs on http://localhost:5000
