---
name: reference-tls-workaround-entorno
description: Como conectar a Supabase/Postgres y hacer git push desde este entorno (inspeccion TLS rompe OpenSSL)
metadata: 
  node_type: memory
  type: reference
  originSessionId: 6b85f0f6-47f5-47ac-b265-0c6728ee4529
---

El entorno hace inspeccion TLS: el CA corporativo no esta en el bundle de OpenSSL/certifi, asi que conexiones HTTPS desde Python y git fallan con `unable to get local issuer certificate` / `CERTIFICATE_VERIFY_FAILED`.

- **Scripts Python (supabase-py, requests, httpx):** instalar `truststore` y al inicio del script `import truststore; truststore.inject_into_ssl()` — usa el almacen de certificados de Windows. (certifi/SSL_CERT_FILE NO basta.)
- **git push/fetch:** usar `git -c http.sslBackend=schannel push ...` (almacen de Windows).
- **Sandbox:** estas operaciones de red requieren `dangerouslyDisableSandbox: true` en Bash.
- El token embebido en la URL del remote git esta EXPIRADO; los push funcionan porque el git-credential-manager de Windows tiene credenciales validas. Si el credential manager se cuelga (varios procesos), matarlos con `taskkill //F //IM git-credential-manager.exe` y reintentar el push con schannel.
