import os
import json
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def lambda_handler(event, context):
    body = event.get("body")
    if body is None:
        data = event
    elif isinstance(body, str):
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {}
    elif isinstance(body, dict):
        data = body
    else:
        data = {}

    email = data.get("email")
    name = data.get("name", "first_name")

    if not email:
        return {"statusCode": 400, "body": "Email es requerido"}

    SENDGRID_API_KEY = os.environ["SENDGRID_API_KEY"]
    SENDER = os.environ["SENDGRID_SENDER"]  # correo verificado en SendGrid

    message = Mail(
        from_email=SENDER,
        to_emails=email,
        subject="Bienvenido a MIWA 🎉",
        plain_text_content=f"Hola {name}, gracias por unirte a MIWA!",
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent to {email}. Status code: {response.status_code}")
        print(response.body)
        print(response.headers)
    except Exception as e:
        print(f"Error sending email to {email}: {e}")
        return {"statusCode": 500, "body": "Error enviando el correo"}
    return {"statusCode": 200, "body": f"Correo enviado a {email} exitosamente"}
