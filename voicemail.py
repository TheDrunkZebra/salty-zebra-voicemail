from flask import Blueprint, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse
import openai
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from src.models.voicemail import db, Voicemail
import logging

voicemail_bp = Blueprint('voicemail', __name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_twilio_client():
    """Initialize Twilio client with credentials from environment"""
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    if not account_sid or not auth_token:
        logger.error("Twilio credentials not found in environment variables")
        return None
    return Client(account_sid, auth_token)

def classify_voicemail(transcription, caller_phone):
    """Use OpenAI to classify the voicemail and generate appropriate response"""
    try:
        openai.api_key = os.getenv('OPENAI_API_KEY')
        
        prompt = f"""
You are a helpful assistant for Salty Zebra Bistro, a modern bistro in Jupiter, FL. 
Analyze this voicemail transcription and provide a classification and personalized response.

Voicemail from {caller_phone}: "{transcription}"

Classify the inquiry as one of:
1. RESERVATION - Customer wants to book a table
2. PRIVATE_EVENT - Customer interested in private events/catering  
3. OFF_THE_MENU - Customer asking about special dishes or off-menu items
4. OTHER - General inquiry, complaint, or other

Respond in this exact JSON format:
{{
    "classification": "RESERVATION|PRIVATE_EVENT|OFF_THE_MENU|OTHER",
    "confidence": "HIGH|MEDIUM|LOW",
    "sms_response": "Personalized SMS response (keep under 160 characters)",
    "action_url": "Relevant URL to include",
    "summary": "Brief summary of the inquiry"
}}

URLs to use:
- RESERVATION: "https://www.opentable.com/r/the-salty-zebra-jupiter-inlet#reserve"
- PRIVATE_EVENT: "https://saltyzebrabistro.com/events"
- OFF_THE_MENU: "https://saltyzebrabistro.com/specials"
- OTHER: "https://saltyzebrabistro.com/contact"

Make the SMS response warm, personal, and include the customer's name if mentioned.
"""

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        import json
        result = json.loads(response.choices[0].message.content)
        return result
        
    except Exception as e:
        logger.error(f"Error classifying voicemail: {str(e)}")
        return {
            "classification": "OTHER",
            "confidence": "LOW",
            "sms_response": "Thanks for calling Salty Zebra! We got your message and will call you back soon.",
            "action_url": "https://saltyzebrabistro.com/contact",
            "summary": "Classification failed"
        }

def send_sms(to_phone, message):
    """Send SMS response using Twilio"""
    try:
        client = get_twilio_client()
        if not client:
            return False
            
        from_phone = os.getenv('TWILIO_PHONE_NUMBER', '+18556062294')
        
        message = client.messages.create(
            body=message,
            from_=from_phone,
            to=to_phone
        )
        
        logger.info(f"SMS sent successfully to {to_phone}: {message.sid}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending SMS to {to_phone}: {str(e)}")
        return False

def send_email_notification(voicemail_data, classification_result):
    """Send email notification to restaurant staff"""
    try:
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        email_user = os.getenv('EMAIL_USER')
        email_password = os.getenv('EMAIL_PASSWORD')
        to_email = os.getenv('NOTIFICATION_EMAIL', 'stephanie@saltyzebrabistro.com')
        
        if not all([email_user, email_password]):
            logger.error("Email credentials not configured")
            return False
        
        msg = MIMEMultipart()
        msg['From'] = email_user
        msg['To'] = to_email
        msg['Subject'] = f"New Voicemail - {classification_result['classification']} - Salty Zebra"
        
        body = f"""
New voicemail received at Salty Zebra Bistro:

From: {voicemail_data.get('From', 'Unknown')}
Classification: {classification_result['classification']} ({classification_result['confidence']} confidence)
Duration: {voicemail_data.get('RecordingDuration', 'Unknown')} seconds

Transcription:
{voicemail_data.get('TranscriptionText', 'Transcription pending...')}

Summary: {classification_result['summary']}

SMS Response Sent:
{classification_result['sms_response']}

Action URL Provided: {classification_result['action_url']}

Recording URL: {voicemail_data.get('RecordingUrl', 'Not available')}

---
Salty Zebra Voicemail System
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(email_user, email_password)
        text = msg.as_string()
        server.sendmail(email_user, to_email, text)
        server.quit()
        
        logger.info(f"Email notification sent to {to_email}")
        return True
        
    except Exception as e:
        logger.error(f"Error sending email notification: {str(e)}")
        return False

@voicemail_bp.route('/webhook', methods=['POST'])
def handle_voicemail_webhook():
    """Handle incoming voicemail webhook from Twilio"""
    try:
        # Get data from Twilio webhook
        caller_phone = request.form.get('From')
        recording_url = request.form.get('RecordingUrl')
        transcription = request.form.get('TranscriptionText', '')
        duration = request.form.get('RecordingDuration')
        
        logger.info(f"Received voicemail from {caller_phone}")
        
        # Save to database
        voicemail = Voicemail(
            caller_phone=caller_phone,
            recording_url=recording_url,
            transcription=transcription,
            duration=int(duration) if duration else None
        )
        
        # Classify the voicemail using AI
        if transcription:
            classification_result = classify_voicemail(transcription, caller_phone)
            voicemail.classification = classification_result['classification']
            voicemail.confidence = classification_result['confidence']
            
            # Create personalized SMS with URL
            sms_message = f"{classification_result['sms_response']}\n\n{classification_result['action_url']}"
            
            # Send SMS response
            sms_success = send_sms(caller_phone, sms_message)
            voicemail.sms_sent = sms_success
            
            # Send email notification
            email_success = send_email_notification(request.form, classification_result)
            voicemail.email_sent = email_success
            
        else:
            logger.warning("No transcription available yet")
            voicemail.classification = "PENDING"
            voicemail.confidence = "LOW"
        
        # Save to database
        db.session.add(voicemail)
        db.session.commit()
        
        return jsonify({"status": "success", "message": "Voicemail processed"}), 200
        
    except Exception as e:
        logger.error(f"Error processing voicemail webhook: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@voicemail_bp.route('/twiml', methods=['GET', 'POST'])
def voicemail_twiml():
    """Generate TwiML for voicemail recording"""
    response = VoiceResponse()
    
    # Professional greeting
    response.say(
        "Thanks for calling Salty Zebra! We're with guests or prepping dinner service. "
        "Leave a message and we'll text you a booking link so you don't wait on hold.",
        voice='Polly.Joanna'
    )
    
    # Record the message
    response.record(
        max_length=120,  # 2 minutes max
        play_beep=True,
        transcribe=True,
        action='/api/voicemail/webhook',  # Webhook URL for processing
        method='POST'
    )
    
    # Confirmation message
    response.say("Got it. We'll text you shortly. Goodbye!", voice='Polly.Joanna')
    
    return str(response), 200, {'Content-Type': 'text/xml'}

@voicemail_bp.route('/test', methods=['POST'])
def test_classification():
    """Test endpoint for AI classification"""
    data = request.get_json()
    transcription = data.get('transcription', '')
    phone = data.get('phone', '+1234567890')
    
    if not transcription:
        return jsonify({"error": "Transcription required"}), 400
    
    result = classify_voicemail(transcription, phone)
    return jsonify(result), 200

@voicemail_bp.route('/recent', methods=['GET'])
def get_recent_voicemails():
    """Get recent voicemails for dashboard"""
    try:
        voicemails = Voicemail.query.order_by(Voicemail.created_at.desc()).limit(20).all()
        return jsonify([vm.to_dict() for vm in voicemails]), 200
    except Exception as e:
        logger.error(f"Error fetching voicemails: {str(e)}")
        return jsonify({"error": str(e)}), 500

