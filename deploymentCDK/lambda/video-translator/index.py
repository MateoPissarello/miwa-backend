"""Lambda function for video translation using AWS Transcribe and Translate - v2"""
import json
import boto3
import logging
import os
import urllib.parse
from typing import Any, Dict, List, Optional

# Configurar logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Clientes AWS
s3_client = boto3.client('s3')
transcribe_client = boto3.client('transcribe')
translate_client = boto3.client('translate')
comprehend_client = boto3.client('comprehend')

# Configuración
BUCKET_NAME = os.environ.get('BUCKET_NAME')
TARGET_LANGUAGES = ['en', 'es', 'fr', 'pt', 'de']  # Idiomas objetivo


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Procesa videos subidos a S3 y genera transcripciones y traducciones."""
    
    try:
        logger.info(f"Evento recibido: {json.dumps(event)}")
        
        # Procesar cada record del evento S3
        for record in event.get('Records', []):
            if record.get('eventSource') == 'aws:s3':
                bucket_name = record['s3']['bucket']['name']
                object_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
                
                logger.info(f"Procesando archivo: {object_key} en bucket: {bucket_name}")
                
                # Verificar si es un archivo de video
                if is_video_file(object_key):
                    process_video(bucket_name, object_key)
                else:
                    logger.info(f"Archivo no es un video, ignorando: {object_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps('Videos procesados exitosamente')
        }
        
    except Exception as e:
        logger.error(f"Error procesando evento: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps(f'Error: {str(e)}')
        }


def is_video_file(file_key: str) -> bool:
    """Verifica si el archivo es un video basándose en su extensión."""
    video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv', '.webm']
    return any(file_key.lower().endswith(ext) for ext in video_extensions)


def process_video(bucket_name: str, object_key: str) -> None:
    """Procesa un video: transcripción y traducción."""
    
    try:
        logger.info(f"Iniciando procesamiento de video: {object_key}")
        
        # 1. Generar nombre único para el job de transcripción
        job_name = generate_job_name(object_key)
        
        # 2. Iniciar transcripción
        transcription_result = start_transcription_job(bucket_name, object_key, job_name)
        
        if transcription_result:
            # 3. Generar traducciones
            process_completed_transcription(transcription_result, object_key, bucket_name)
        else:
            logger.error(f"Falló la transcripción para {object_key}")
        
    except Exception as e:
        logger.error(f"Error procesando video {object_key}: {str(e)}")


def generate_job_name(object_key: str) -> str:
    """Genera un nombre único para el job de transcripción."""
    import time
    import re
    # Remover caracteres no válidos (solo permitir [0-9a-zA-Z._-])
    clean_name = re.sub(r'[^0-9a-zA-Z._-]', '_', object_key)
    timestamp = int(time.time())
    job_name = f"miwa-transcription-{clean_name}-{timestamp}"
    # Asegurar que no exceda 200 caracteres (límite de Transcribe)
    return job_name[:200]


def get_media_format(file_key: str) -> str:
    """Determina el formato de media basándose en la extensión del archivo."""
    extension = file_key.lower().split('.')[-1]
    format_mapping = {
        'mp4': 'mp4',
        'mov': 'mov',
        'avi': 'avi',
        'mkv': 'mkv',
        'wmv': 'wmv',
        'flv': 'flv',
        'webm': 'webm',
    }
    return format_mapping.get(extension, 'mp4')  # Default a mp4


def start_transcription_job(bucket_name: str, object_key: str, job_name: str) -> Optional[Dict[str, Any]]:
    """Inicia un job de transcripción en AWS Transcribe."""
    
    try:
        media_uri = f"s3://{bucket_name}/{object_key}"
        media_format = get_media_format(object_key)
        
        logger.info(f"Iniciando transcripción para: {media_uri}")
        
        # Extraer usuario del path para guardar transcripción en su carpeta
        # Formato: {usuario_email}/uploads/{archivo}
        path_parts = object_key.split('/')
        if len(path_parts) >= 3 and path_parts[1] == 'uploads':
            user_email = path_parts[0]
            output_key = f"{user_email}/transcriptions/{job_name}.json"
        else:
            # Fallback
            output_key = f"transcriptions/{job_name}.json"
        
        # Configurar el job de transcripción
        job_config = {
            'TranscriptionJobName': job_name,
            'Media': {'MediaFileUri': media_uri},
            'MediaFormat': media_format,
            'IdentifyLanguage': True,  # Detección automática de idioma
            'OutputBucketName': bucket_name,
            'OutputKey': output_key,
        }
        
        # Iniciar el job
        response = transcribe_client.start_transcription_job(**job_config)
        logger.info(f"Job de transcripción iniciado: {job_name}")
        
        # Esperar a que el job termine
        return wait_for_transcription_job(job_name)
        
    except Exception as e:
        logger.error(f"Error iniciando transcripción: {str(e)}")
        return None


def wait_for_transcription_job(job_name: str, max_wait_time: int = 600) -> Optional[Dict[str, Any]]:
    """Espera a que termine el job de transcripción."""
    
    import time
    start_time = time.time()
    
    while time.time() - start_time < max_wait_time:
        try:
            response = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
            status = response['TranscriptionJob']['TranscriptionJobStatus']
            
            logger.info(f"Estado del job {job_name}: {status}")
            
            if status == 'COMPLETED':
                return response['TranscriptionJob']
            elif status == 'FAILED':
                logger.error(f"Job de transcripción falló: {job_name}")
                return None
            
            # Esperar antes de verificar de nuevo
            time.sleep(30)
            
        except Exception as e:
            logger.error(f"Error verificando estado del job: {str(e)}")
            return None
    
    logger.error(f"Timeout esperando job de transcripción: {job_name}")
    return None


def process_completed_transcription(transcription_job: Dict[str, Any], original_key: str, bucket_name: str) -> None:
    """Procesa el resultado de la transcripción y genera traducciones."""
    
    try:
        # Obtener el texto transcrito desde nuestro bucket
        job_name = transcription_job['TranscriptionJobName']
        
        # Determinar la ubicación del archivo de transcripción según el path original
        path_parts = original_key.split('/')
        if len(path_parts) >= 3 and path_parts[1] == 'uploads':
            user_email = path_parts[0]
            transcript_key = f"{user_email}/transcriptions/{job_name}.json"
        else:
            # Fallback
            transcript_key = f"transcriptions/{job_name}.json"
        
        transcript_text = get_transcript_text_from_s3(bucket_name, transcript_key)
        
        if not transcript_text:
            logger.error("No se pudo obtener el texto transcrito")
            return
        
        # Detectar idioma original
        detected_language = detect_language(transcript_text)
        logger.info(f"Idioma detectado: {detected_language}")
        
        # Generar traducciones
        translations = {}
        for target_lang in TARGET_LANGUAGES:
            if target_lang != detected_language:
                translated_text = translate_text(transcript_text, detected_language, target_lang)
                if translated_text:
                    translations[target_lang] = translated_text
        
        # Preparar resultado final
        completion_time = transcription_job.get('CompletionTime', '')
        if completion_time and hasattr(completion_time, 'isoformat'):
            completion_time = completion_time.isoformat()
        
        result = {
            'original_file': original_key,
            'original_language': detected_language,
            'original_text': transcript_text,
            'translations': translations,
            'processed_at': str(completion_time),
        }
        
        # Guardar resultado en S3
        save_translation_result(bucket_name, original_key, result)
        
    except Exception as e:
        logger.error(f"Error procesando transcripción completada: {str(e)}")


def get_transcript_text_from_s3(bucket_name: str, transcript_key: str) -> Optional[str]:
    """Obtiene el texto del archivo de transcripción desde S3."""
    
    try:
        logger.info(f"Leyendo transcripción desde s3://{bucket_name}/{transcript_key}")
        
        # Descargar el archivo de transcripción desde nuestro bucket
        response = s3_client.get_object(Bucket=bucket_name, Key=transcript_key)
        transcript_data = json.loads(response['Body'].read().decode('utf-8'))
        
        # Extraer el texto
        if 'results' in transcript_data and 'transcripts' in transcript_data['results']:
            transcripts = transcript_data['results']['transcripts']
            if transcripts and len(transcripts) > 0:
                text = transcripts[0].get('transcript', '')
                logger.info(f"Texto transcrito extraído exitosamente ({len(text)} caracteres)")
                return text
        
        logger.error("No se encontró texto en el archivo de transcripción")
        return None
        
    except Exception as e:
        logger.error(f"Error obteniendo texto de transcripción: {str(e)}")
        return None


def detect_language(text: str) -> str:
    """Detecta el idioma del texto usando AWS Comprehend."""
    
    try:
        response = comprehend_client.detect_dominant_language(Text=text[:5000])  # Límite de caracteres
        languages = response.get('Languages', [])
        if languages:
            detected_lang = languages[0]['LanguageCode']
            logger.info(f"Idioma detectado: {detected_lang} (confianza: {languages[0]['Score']})")
            return detected_lang
        
        return 'en'  # Default a inglés
        
    except Exception as e:
        logger.error(f"Error detectando idioma: {str(e)}")
        return 'en'


def translate_text(text: str, source_lang: str, target_lang: str) -> Optional[str]:
    """Traduce texto usando AWS Translate."""
    
    try:
        # AWS Translate tiene límite de caracteres, dividir si es necesario
        max_chars = 5000
        if len(text) <= max_chars:
            response = translate_client.translate_text(
                Text=text,
                SourceLanguageCode=source_lang,
                TargetLanguageCode=target_lang
            )
            return response['TranslatedText']
        else:
            # Dividir texto en chunks
            chunks = [text[i:i+max_chars] for i in range(0, len(text), max_chars)]
            translated_chunks = []
            
            for chunk in chunks:
                response = translate_client.translate_text(
                    Text=chunk,
                    SourceLanguageCode=source_lang,
                    TargetLanguageCode=target_lang
                )
                translated_chunks.append(response['TranslatedText'])
            
            return ' '.join(translated_chunks)
            
    except Exception as e:
        logger.error(f"Error traduciendo texto de {source_lang} a {target_lang}: {str(e)}")
        return None


def save_translation_result(bucket_name: str, original_key: str, result: Dict[str, Any]) -> None:
    """Guarda el resultado de la traducción en S3 manteniendo estructura de usuario."""
    
    try:
        # Extraer usuario y nombre de archivo del path original
        # Formato esperado: {usuario_email}/uploads/{archivo}
        path_parts = original_key.split('/')
        
        if len(path_parts) >= 3 and path_parts[1] == 'uploads':
            user_email = path_parts[0]
            file_name = path_parts[-1]
            base_name = file_name.rsplit('.', 1)[0]  # Remover extensión
            
            # Guardar en /{usuario}/transcriptions/{archivo}_translations.json
            result_key = f"{user_email}/transcriptions/{base_name}_translations.json"
        else:
            # Fallback si el path no tiene el formato esperado
            base_name = original_key.rsplit('.', 1)[0]
            result_key = f"translations/{base_name}_translations.json"
        
        # Guardar en S3
        s3_client.put_object(
            Bucket=bucket_name,
            Key=result_key,
            Body=json.dumps(result, ensure_ascii=False, indent=2),
            ContentType='application/json',
            Metadata={
                'original-file': original_key,
                'processed-by': 'miwa-video-translator'
            }
        )
        
        logger.info(f"Resultado de traducción guardado en: s3://{bucket_name}/{result_key}")
        
    except Exception as e:
        logger.error(f"Error guardando resultado: {str(e)}")