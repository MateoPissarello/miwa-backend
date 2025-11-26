# Migración: Eliminación de Aurora RDS

## Resumen de Cambios

Se ha eliminado completamente la base de datos Aurora RDS del stack de backend, ya que la aplicación usa AWS Cognito para autenticación y no requiere una base de datos relacional.

## Cambios Realizados

### 1. CDK Stack (`deploymentCDK/lib/miwa-backend-stack.ts`)
- ✅ Eliminado el cluster de Aurora Serverless v2
- ✅ Eliminado el security group de la base de datos
- ✅ Eliminadas las variables de entorno relacionadas con DB (DB_HOST, DB_PORT, DB_NAME)
- ✅ Eliminados los secretos de DB del contenedor (DB_USER, DB_PASSWORD, DB_SECRET_ARN)
- ✅ Eliminada la regla de conexión entre el servicio backend y Aurora
- ✅ Eliminado el import de `aws-cdk-lib/aws-rds`

### 2. Backend - Configuración
- ✅ Eliminadas variables de configuración de DB en `core/config.py`:
  - DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
  - Propiedad DATABASE_URL
- ✅ Eliminada la inicialización de la base de datos en `kernel/kernel.py`
- ✅ Eliminado el archivo `database.py` (configuración de SQLAlchemy)
- ✅ Eliminado el archivo `models.py` (modelo User de SQLAlchemy)

### 3. Backend - Servicios
- ✅ Eliminado `services/auth_service/router.py` (endpoints de login/signup tradicional)
- ✅ Eliminado `services/auth_service/functions.py` (funciones CRUD de usuarios)
- ✅ Eliminado `utils/login_logic.py` (lógica de login con DB)
- ✅ Actualizado `services/auth_service/plugin.py` para solo incluir el router de Cognito
- ✅ Actualizado `services/s3_service/router.py` para eliminar la dependencia de `get_db`

### 4. Backend - Migraciones y Dependencias
- ✅ Eliminado directorio `migrations/` (Alembic)
- ✅ Eliminado `alembic.ini`
- ✅ Actualizadas dependencias en `requirements.txt`:
  - Eliminado: alembic, SQLAlchemy, psycopg2-binary, greenlet, Mako, MarkupSafe

## Endpoints Eliminados

Los siguientes endpoints ya NO están disponibles:

- `POST /api/auth/login` - Login tradicional con email/password
- `POST /api/auth/admin/login` - Login de administradores
- `POST /api/auth/signup` - Registro de usuarios
- `DELETE /api/auth/delete/{user_id}` - Eliminar usuarios
- `GET /api/auth/users` - Listar usuarios
- `PUT /api/auth/update/{user_id}` - Actualizar usuarios

## Endpoints Disponibles (Cognito)

La autenticación ahora se realiza exclusivamente a través de AWS Cognito:

- `POST /api/auth/cognito/signup` - Registro con Cognito
- `POST /api/auth/cognito/confirm` - Confirmar registro
- `POST /api/auth/cognito/login` - Login con Cognito
- `POST /api/auth/cognito/mfa/setup/begin` - Iniciar configuración MFA
- `POST /api/auth/cognito/mfa/setup/verify` - Verificar configuración MFA
- `POST /api/auth/cognito/mfa/challenge` - Desafío MFA

## Próximos Pasos

### Para Desplegar los Cambios:

1. **Actualizar el stack de CDK:**
   ```bash
   cd deploymentCDK
   npm install
   cdk diff MiwaBackendStack
   cdk deploy MiwaBackendStack
   ```

2. **Reconstruir la imagen del backend:**
   ```bash
   cd backend
   docker build -t miwa-backend .
   ```

3. **Actualizar las variables de entorno:**
   - Eliminar de AWS Secrets Manager o del archivo `.env`:
     - DB_USER
     - DB_PASSWORD
     - DB_HOST
     - DB_PORT
     - DB_NAME

### Consideraciones Importantes:

⚠️ **ADVERTENCIA**: Si tienes datos de usuarios en la base de datos Aurora actual, asegúrate de migrarlos a Cognito antes de eliminar el stack.

💰 **Ahorro de Costos**: Aurora Serverless v2 tiene un costo mínimo de ~$43/mes (0.5 ACU). Al eliminarlo, ahorrarás este costo mensual.

🔒 **Seguridad**: Cognito es un servicio administrado por AWS que proporciona autenticación segura, escalable y con características avanzadas (MFA, OAuth, etc.).

## Rollback

Si necesitas revertir estos cambios:

1. Restaura los archivos eliminados desde el control de versiones
2. Vuelve a desplegar el stack anterior de CDK
3. Ejecuta las migraciones de Alembic para recrear las tablas
