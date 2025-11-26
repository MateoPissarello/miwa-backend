# Instrucciones de Despliegue - Eliminación de Aurora RDS

## ⚠️ IMPORTANTE: Antes de Desplegar

### 1. Backup de Datos (si aplica)
Si tienes usuarios registrados en la base de datos Aurora actual, **debes migrarlos a Cognito** antes de continuar:

```bash
# Exportar usuarios de Aurora (si los hay)
# Este script es solo un ejemplo, ajústalo según tu necesidad
psql -h <DB_HOST> -U <DB_USER> -d miwa_backend -c "COPY users TO STDOUT CSV HEADER" > users_backup.csv
```

### 2. Verificar que Cognito está Configurado
Asegúrate de que tu User Pool de Cognito está correctamente configurado con:
- ✅ Políticas de contraseña
- ✅ Atributos requeridos (email, etc.)
- ✅ Verificación de email
- ✅ MFA (opcional)
- ✅ App Client configurado

## 📋 Pasos de Despliegue

### Paso 1: Revisar los Cambios

```bash
# Ver todos los archivos modificados
git status

# Ver los cambios en detalle
git diff

# Revisar los archivos eliminados
git ls-files --deleted
```

### Paso 2: Actualizar Variables de Entorno

Edita tu archivo `.env` o AWS Secrets Manager y **elimina** las siguientes variables:

```bash
# Variables a ELIMINAR:
DB_USER=
DB_PASSWORD=
DB_HOST=
DB_PORT=
DB_NAME=
```

Las variables que **deben permanecer**:
```bash
# Cognito
COGNITO_USER_POOL_ID=
COGNITO_CLIENT_ID=
COGNITO_SECRET=
AWS_REGION=

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=
GOOGLE_AFTER_CONNECT=
DYNAMO_GOOGLE_TOKENS_TABLE=
GOOGLE_STATE_SECRET=

# S3 y otros servicios
S3_BUCKET_ARN=
BUCKET_NAME=
API_GATEWAY_URL=
DDB_TABLE_NAME=
PIPELINE_STATE_MACHINE_ARN=

# Configuración general
SECRET_KEY=
ALGORITHM=
ACCESS_TOKEN_EXPIRE_MINUTES=
LLM_MODEL_ID=
LLM_MAX_TOKENS=
DEFAULT_URL_TTL_SEC=
ALLOW_EXTS=
```

### Paso 3: Actualizar AWS Secrets Manager

```bash
# Obtener el secreto actual
aws secretsmanager get-secret-value \
  --secret-id dev/miwa/app \
  --region us-east-1 \
  --query SecretString \
  --output text > current_secret.json

# Editar el archivo y eliminar las claves de DB
# DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

# Actualizar el secreto
aws secretsmanager update-secret \
  --secret-id dev/miwa/app \
  --region us-east-1 \
  --secret-string file://current_secret.json

# Limpiar el archivo temporal
rm current_secret.json
```

### Paso 4: Desplegar el Stack de CDK

```bash
# Navegar al directorio de CDK
cd deploymentCDK

# Instalar dependencias (si es necesario)
npm install

# Ver los cambios que se aplicarán
cdk diff MiwaBackendStack

# Desplegar el stack
cdk deploy MiwaBackendStack

# Confirmar cuando se solicite
# ⚠️ Esto eliminará el cluster de Aurora RDS
```

**Salida esperada:**
```
✅ MiwaBackendStack

Outputs:
MiwaBackendStack.ServiceUrl = https://app.tudominio.com
MiwaBackendStack.BackendRepositoryUri = 225989373192.dkr.ecr.us-east-1.amazonaws.com/miwa-backend
MiwaBackendStack.FrontendRepositoryUri = 225989373192.dkr.ecr.us-east-1.amazonaws.com/miwa-frontend
MiwaBackendStack.LoadBalancerDnsName = MiwaALB-xxxxx.us-east-1.elb.amazonaws.com
```

### Paso 5: Reconstruir y Desplegar la Imagen del Backend

```bash
# Navegar al directorio del backend
cd ../backend

# Construir la nueva imagen Docker
docker build -t miwa-backend:latest .

# Autenticarse en ECR
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin \
  225989373192.dkr.ecr.us-east-1.amazonaws.com

# Etiquetar la imagen
docker tag miwa-backend:latest \
  225989373192.dkr.ecr.us-east-1.amazonaws.com/miwa-backend:latest

# Subir la imagen
docker push 225989373192.dkr.ecr.us-east-1.amazonaws.com/miwa-backend:latest
```

### Paso 6: Actualizar el Servicio ECS

```bash
# Forzar un nuevo despliegue del servicio
aws ecs update-service \
  --cluster MiwaBackendStack-MiwaCluster \
  --service backend-service \
  --force-new-deployment \
  --region us-east-1

# Monitorear el despliegue
aws ecs describe-services \
  --cluster MiwaBackendStack-MiwaCluster \
  --services backend-service \
  --region us-east-1 \
  --query 'services[0].deployments'
```

### Paso 7: Verificar el Despliegue

```bash
# Verificar que el servicio está corriendo
aws ecs describe-services \
  --cluster MiwaBackendStack-MiwaCluster \
  --services backend-service \
  --region us-east-1 \
  --query 'services[0].runningCount'

# Debería retornar: 1 (o el número de instancias deseadas)

# Probar el endpoint de health
curl https://app.tudominio.com/api/health

# Debería retornar: {"message":"¡Bienvenido a la API de MIWA!"}
```

### Paso 8: Probar la Autenticación con Cognito

```bash
# Probar el registro
curl -X POST https://app.tudominio.com/api/auth/cognito/signup \
  -H "Content-Type: application/json" \
  -d '{
    "nickname": "testuser",
    "email": "test@example.com",
    "password": "TestPassword123!"
  }'

# Probar el login (después de confirmar el email)
curl -X POST https://app.tudominio.com/api/auth/cognito/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test@example.com",
    "password": "TestPassword123!"
  }'
```

## 🧹 Limpieza (Opcional)

### Eliminar el Cluster de Aurora Manualmente (si quedó)

Si por alguna razón el cluster de Aurora no se eliminó automáticamente:

```bash
# Listar clusters
aws rds describe-db-clusters --region us-east-1

# Eliminar el cluster (ajusta el nombre)
aws rds delete-db-cluster \
  --db-cluster-identifier miwadatabase-xxxxx \
  --skip-final-snapshot \
  --region us-east-1
```

### Eliminar Snapshots de Aurora

```bash
# Listar snapshots
aws rds describe-db-cluster-snapshots --region us-east-1

# Eliminar snapshots (si los hay)
aws rds delete-db-cluster-snapshot \
  --db-cluster-snapshot-identifier snapshot-name \
  --region us-east-1
```

## 🔍 Troubleshooting

### Error: "Module 'database' not found"
**Solución**: Asegúrate de que la nueva imagen Docker se construyó y desplegó correctamente.

### Error: "DB_USER environment variable not set"
**Solución**: Actualiza el secreto en AWS Secrets Manager y reinicia el servicio ECS.

### Error: El servicio no inicia
**Solución**: Revisa los logs de CloudWatch:
```bash
aws logs tail /aws/ecs/miwa-backend --follow --region us-east-1
```

### Error: "Operation not permitted" en endpoints protegidos
**Solución**: Esto es esperado. El RoleChecker ahora permite todos los usuarios autenticados. Si necesitas verificación de roles, implementa la lógica de grupos de Cognito (ver TODO en `RoleChecker.py`).

## 📊 Verificación de Costos

Después del despliegue, verifica que los costos de Aurora hayan desaparecido:

```bash
# Ver costos de RDS en los últimos 7 días
aws ce get-cost-and-usage \
  --time-period Start=2025-11-18,End=2025-11-25 \
  --granularity DAILY \
  --metrics BlendedCost \
  --filter file://rds-filter.json

# Contenido de rds-filter.json:
# {
#   "Dimensions": {
#     "Key": "SERVICE",
#     "Values": ["Amazon Relational Database Service"]
#   }
# }
```

## ✅ Checklist Final

- [ ] Backup de datos realizado (si aplica)
- [ ] Variables de entorno actualizadas
- [ ] AWS Secrets Manager actualizado
- [ ] CDK desplegado exitosamente
- [ ] Imagen Docker reconstruida y subida
- [ ] Servicio ECS actualizado
- [ ] Endpoint de health responde correctamente
- [ ] Autenticación con Cognito funciona
- [ ] Endpoints de S3 funcionan
- [ ] Cluster de Aurora eliminado
- [ ] Costos verificados

## 🎉 ¡Listo!

Tu aplicación ahora usa exclusivamente AWS Cognito para autenticación y ya no depende de Aurora RDS.

**Ahorro estimado**: ~$43/mes
**Complejidad reducida**: -6 archivos, -200 líneas de código
**Mantenimiento**: Sin migraciones de base de datos
