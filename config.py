# API endpoints
API_BASE = "https://api.simpliroute.com/v1"
API_VISITS_REPORTS = "https://api.simpliroute.com/v1/reports/visits"
API_ROUTES_REPORTS = "https://api-gateway.simpliroute.com/v1/reports/routes"
API_SEND_WEBHOOKS = "https://api.simpliroute.com/v1/mobile/send-webhooks"
API_SEND_PLAN_WEBHOOKS = "https://api.simpliroute.com/v1/mobile/send-plan-webhooks"
API_SEND_ROUTE_WEBHOOKS = "https://api.simpliroute.com/v1/mobile/send-route-webhooks"
API_SEND_ON_ITS_WAY_WEBHOOKS = "https://api.simpliroute.com/v1/mobile/send-on-its-way-webhooks"
API_EVENTS_REGISTER = "https://api-mobile.simpliroute.com/v1/events/register/"

# Timeouts and delays (seconds)
REQUEST_TIMEOUT = 60
CLEANUP_TIMEOUT = 600
WEBHOOK_DELAY = 0.4
EDIT_DELAY = 0.5
REPORT_DELAY = 3

# Retry policy (5xx errors)
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, doubles each attempt (2, 4, 8)

# Bulk edit
EDIT_TIMEOUT = 240
MAX_BLOCK_SIZE = 400
CLEANUP_NUM_BATCHES = 5

# Validador de Plan
MAX_SMALLINT_FIELD = 32767  # limite del campo SmallInteger de SimpliRoute para *_percentage; superarlo bloquea el guardado del plan

# Motivos de Rechazo
OBSERVATION_DELAY = 0.3  # seconds between create/delete requests

# Consulta Extensiones
EXTENSIONES_QUERY_LIMIT = 500  # cap de filas por consulta (la tabla no filtra por cuenta propia, puede haber decenas de miles)
EXTENSIONES_MIN_SEARCH_LEN = 3  # minimo de caracteres antes de permitir buscar
