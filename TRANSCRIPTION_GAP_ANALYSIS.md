# Cobertura actual vs. flujo solicitado de transcripciones

## Lo que implementa el backend
- Endpoints HTTP expuestos en el plugin de transcripciones:
  - `GET /api/recordings` lista las grabaciones del usuario, codifica el `recording_id` y adjunta el estado inferido desde DynamoDB y la existencia del archivo en S3.【F:backend/services/transcription_service/router.py†L174-L256】
  - `POST /api/transcriptions/{recording_id}/start` lanza un trabajo de Amazon Transcribe desde la propia API (no desde un trigger de S3), validando la propiedad del archivo y guardando estados en DynamoDB.【F:backend/services/transcription_service/router.py†L259-L327】
  - `GET /api/transcriptions/{recording_id}/status` devuelve el estado persistido/inferido de la transcripción.【F:backend/services/transcription_service/router.py†L330-L377】
  - `GET /api/transcriptions/{recording_id}` descarga el `.txt` desde S3 y lo retorna al cliente.【F:backend/services/transcription_service/router.py†L380-L410】
- El texto transcrito se guarda en la ruta `transcripciones/{email}/{nombre_archivo}.txt` en S3.【F:backend/services/transcription_service/utils.py†L6-L36】
- Los estados manejados son `INICIANDO_TRANSCRIPCION`, `EN_PROCESO`, `TRANSCRIPCION_COMPLETADA` y `ERROR`, guardados en DynamoDB con llave de partición `recording_id`.【F:backend/services/transcription_service/utils.py†L6-L36】【F:backend/services/transcription_service/repository.py†L10-L37】
- El arranque de la transcripción es sincrónico: el endpoint inicia el job de Transcribe, hace polling hasta completarlo o error, luego escribe el `.txt` en S3 y actualiza DynamoDB antes de responder.【F:backend/services/transcription_service/router.py†L89-L171】【F:backend/services/transcription_service/router.py†L259-L327】

## Diferencias frente al flujo solicitado
- No existe un disparador automático al subir archivos a S3; el backend requiere que el cliente llame manualmente a `POST /api/transcriptions/{recording_id}/start` para iniciar cada transcripción.
- No hay una Lambda dedicada que procese eventos de S3 ni que formatee/guarde transcripciones de manera asíncrona; la lógica vive dentro del endpoint y se ejecuta en el contenedor del backend.
- No se ha añadido infraestructura de DynamoDB/S3/Lambda en CDK para orquestar ese flujo automático; solo se consume una tabla DynamoDB preexistente indicada por `DYNAMO_TRANSCRIPTIONS_TABLE`.

## Qué puede usar el frontend hoy
- Para renderizar la tabla y el modal descritos, puede consumir los endpoints ya expuestos:
  - `GET /api/recordings`
  - `GET /api/transcriptions/{recording_id}/status`
  - `GET /api/transcriptions/{recording_id}`
- Si necesita disparar la transcripción desde la UI, debe llamar a `POST /api/transcriptions/{recording_id}/start` hasta que exista un flujo automático por S3.
