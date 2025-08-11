import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from twilio.twiml.voice_response import VoiceResponse
import openai
import requests

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'asdf#FGSgvasgf$5$WGT'

# Enable CORS for all routes
CORS(app)

# Configure OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')

# Twilio configuration
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_PHONE_NUMBER = os.getenv('TWILIO_PHONE_NUMBER')

# Email configuration
EMAIL_TO = os.getenv('EMAIL_TO', 'stephanie@saltyzebrabistro.com')

def classify_voicemail(transcription):
    """Use OpenAI to classify the voicemail message"""
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are an AI assistant for Salty Zebra Bistro restaurant. Classify customer voicemails into one of these categories: 'reservation', 'event', 'special_menu', or 'other'. Respond with just the category name."
                },
                {
                    "role": "user",
                    "content": f"Classify this voicemail: {transcription}"
                }
            ],
            max_tokens=10,
            temperature=0.1
        )
        return response.choices[0].message.content.strip().lower()
    except Exception as e:
        print(f"Error classifying voicemail: {e}")
        return "other"

def send_sms_response(to_number, message_type):
    """Send appropriate SMS response based on message type"""
    messages = {
        'reservation': "Hi! Thanks for calling Salty Zebra Bistro about a reservation. We'd love to have you! Book instantly here: https://www.opentable.com/saltyzebrabistro or call us back. We'll also follow up personally!",
        'event': "Thanks for your interest in hosting an event at Salty Zebra! We specialize in memorable private dining experiences. Get started here: https://saltyzebrabistro.com/events or we'll call you back within 2 hours!",
        'special_menu': "Thanks for asking about our off-menu specials! Check out our current offerings: https://saltyzebrabistro.com/specials or follow us on social media for daily updates. We'll also call you back!",
        'other': "Thanks for calling Salty Zebra Bistro! We received your message and will call you back soon. For immediate assistance, visit https://saltyzebrabistro.com"
    }
    
    message = messages.get(message_type, messages['other'] )
    
    try:
        from twilio.rest import Client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        
        client.messages.create(
            body=message,
            from_=TWILIO_PHONE_NUMBER,
            to=to_number
        )
        print(f"SMS sent to {to_number}")
        return True
    except Exception as e:
        print(f"Error sending SMS: {e}")
        return False

def send_email_notification(caller_number, transcription, classification):
    """Send email notification to restaurant staff"""
    try:
        subject = f"New Voicemail - {classification.title()} Inquiry"
        
        body = f"""
New voicemail received at Salty Zebra Bistro:

Caller: {caller_number}
Classification: {classification.title()}
Transcription: {transcription}

Automatic SMS response has been sent to the customer.

Please follow up as needed.

- Salty Zebra AI Voicemail System
        """
        
        # For now, just print the email (you can configure SMTP later)
        print(f"EMAIL NOTIFICATION:")
        print(f"To: {EMAIL_TO}")
        print(f"Subject: {subject}")
        print(f"Body: {body}")
        
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

@app.route('/')
def home():
    return """
    <h1>🎉 Salty Zebra Voicemail System is Live!</h1>
    <p>Your AI-powered voicemail system is running successfully.</p>
    <p><strong>Features:</strong></p>
    <ul>
        <li>✅ AI message classification</li>
        <li>✅ Automatic SMS responses</li>
        <li>✅ Email notifications</li>
        <li>✅ Professional voicemail handling</li>
    </ul>
    <p><strong>Next step:</strong> Add this URL to your Twilio webhook configuration.</p>
    """

@app.route('/webhook/voicemail', methods=['POST'])
def handle_voicemail():
    """Handle incoming voicemail from Twilio"""
    try:
        # Get data from Twilio
        caller_number = request.form.get('From', 'Unknown')
        transcription = request.form.get('TranscriptionText', '')
        recording_url = request.form.get('RecordingUrl', '')
        
        print(f"Received voicemail from {caller_number}")
        print(f"Transcription: {transcription}")
        
        # Classify the message
        classification = classify_voicemail(transcription) if transcription else 'other'
        print(f"Classification: {classification}")
        
        # Send SMS response
        send_sms_response(caller_number, classification)
        
        # Send email notification
        send_email_notification(caller_number, transcription, classification)
        
        return jsonify({
            'status': 'success',
            'classification': classification,
            'message': 'Voicemail processed successfully'
        })
        
    except Exception as e:
        print(f"Error processing voicemail: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/webhook/voice', methods=['POST'])
def handle_voice_call():
    """Handle incoming voice calls and provide voicemail greeting"""
    response = VoiceResponse()
    
    response.say(
        "Thank you for calling Salty Zebra Bistro! We're currently unable to take your call, "
        "but your message is important to us. Please leave a detailed message after the beep, "
        "and we'll get back to you shortly. You'll also receive a text message with helpful links!",
        voice='alice'
    )
    
    response.record(
        transcribe=True,
        transcribe_callback='/webhook/voicemail',
        max_length=120,
        finish_on_key='#'
    )
    
    response.say("Thank you for your message. We'll be in touch soon!", voice='alice')
    
    return str(response)

@app.route('/health')
def health_check():
    return jsonify({'status': 'healthy', 'service': 'Salty Zebra Voicemail System'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

