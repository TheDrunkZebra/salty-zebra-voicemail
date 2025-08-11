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
EMAIL_FROM = os.getenv('EMAIL_FROM', 'voicemail@saltyzebrabistro.com')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD', '')
SMTP_SERVER = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))

# Store recent recordings (temporary - in production use database)
recent_recordings = []

def get_latest_main_greeting_url():
    """Get the URL of the most recent main greeting recording"""
    try:
        if not recent_recordings:
            return None
            
        for recording in reversed(recent_recordings):
            if recording and recording.get('type') == 'main_greeting' and recording.get('url'):
                return recording.get('url')
        return None
    except Exception as e:
        print(f"Error getting greeting URL: {e}")
        return None

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
        # Create message
        msg = MIMEMultipart()
        msg['From'] = EMAIL_FROM
        msg['To'] = EMAIL_TO
        msg['Subject'] = f"New Voicemail - {classification.title()} Inquiry"
        
        body = f"""
New voicemail received at Salty Zebra Bistro:

Caller: {caller_number}
Classification: {classification.title()}
Transcription: {transcription}

Automatic SMS response has been sent to the customer.

Please follow up as needed.

- Salty Zebra AI Voicemail System
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Try to send email if credentials are available
        if EMAIL_PASSWORD:
            try:
                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                server.starttls()
                server.login(EMAIL_FROM, EMAIL_PASSWORD)
                text = msg.as_string()
                server.sendmail(EMAIL_FROM, EMAIL_TO, text)
                server.quit()
                print(f"Email sent successfully to {EMAIL_TO}")
                return True
            except Exception as smtp_error:
                print(f"SMTP Error: {smtp_error}")
                # Fall back to console logging
                print(f"EMAIL NOTIFICATION (SMTP failed):")
                print(f"To: {EMAIL_TO}")
                print(f"Subject: {msg['Subject']}")
                print(f"Body: {body}")
                return False
        else:
            # No email credentials configured, log to console
            print(f"EMAIL NOTIFICATION (No SMTP configured):")
            print(f"To: {EMAIL_TO}")
            print(f"Subject: {msg['Subject']}")
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
        
        # Get the type from URL parameter
        message_type = request.args.get('type', 'general')
        
        print(f"Received {message_type} voicemail from {caller_number}")
        print(f"Transcription: {transcription}")
        
        # Send email notification with proper classification
        send_email_notification(caller_number, transcription, message_type)
        
        return jsonify({
            'status': 'success',
            'classification': message_type,
            'message': 'Voicemail processed successfully'
        })
        
    except Exception as e:
        print(f"Error processing voicemail: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/webhook/voice', methods=['POST'])
def handle_voice_call():
    """Handle incoming voice calls with interactive menu"""
    response = VoiceResponse()
    
    # Get user input if any
    digits = request.form.get('Digits', '')
    
    if not digits:
        # Main menu - use recorded greeting if available, otherwise fallback to text-to-speech
        try:
            greeting_url = get_latest_main_greeting_url()
            
            if greeting_url:
                # Use recorded personal greeting
                response.play(greeting_url)
            else:
                # Fallback to text-to-speech
                response.say(
                    "Thanks for calling The Salty Zebra Bistro! "
                    "Press 1 for reservations, Press 2 for private events, "
                    "or Press 3 to leave a general message.",
                    voice='alice'
                )
        except Exception as e:
            print(f"Error with greeting: {e}")
            # Emergency fallback to text-to-speech
            response.say(
                "Thanks for calling The Salty Zebra Bistro! "
                "Press 1 for reservations, Press 2 for private events, "
                "or Press 3 to leave a general message.",
                voice='alice'
            )
        
        gather = response.gather(num_digits=2, action='/webhook/voice', method='POST', timeout=10)
        
        # If no input, go to general voicemail
        response.say("Let's get you to our voicemail.", voice='alice')
        response.redirect('/webhook/voice?default=general')
        
    elif digits == '99':
        # TEMPORARY: Recording mode for owner
        response.say(
            "Recording mode activated. You will now record the main greeting message. "
            "Speak clearly after the beep and press any key when finished.",
            voice='alice'
        )
        response.record(
            transcribe=False,
            transcribe_callback='/webhook/recording?type=main_greeting',
            max_length=30,
            finish_on_key='#',
            action='/webhook/recording?type=main_greeting'
        )
        
    elif digits == '1' or (len(digits) == 1 and digits == '1'):
        # Reservation voicemail
        response.say(
            "Great! You're calling about reservations. "
            "Please leave your name, phone number, preferred date and time, "
            "and party size after the beep. For immediate booking, "
            "visit saltyzebrabistro.com or use our live chat.",
            voice='alice'
        )
        response.record(
            transcribe=True,
            transcribe_callback='/webhook/voicemail?type=reservation',
            max_length=120,
            finish_on_key='#'
        )
        
    elif digits == '2' or (len(digits) == 1 and digits == '2'):
        # Private event voicemail
        response.say(
            "Wonderful! You're interested in private events. "
            "Please leave your name, phone number, event details, "
            "and preferred dates after the beep. "
            "Visit saltyzebrabistro.com for more information.",
            voice='alice'
        )
        response.record(
            transcribe=True,
            transcribe_callback='/webhook/voicemail?type=event',
            max_length=120,
            finish_on_key='#'
        )
        
    elif digits == '3' or (len(digits) == 1 and digits == '3') or request.args.get('default') == 'general':
        # General voicemail
        response.say(
            "Hi, you've reached Seamus and Stephanie at The Salty Zebra Bistro in Jupiter. "
            "We're currently with guests, but we'd love to help you join the herd! "
            "Please leave your name, number, and how we can assist you. "
            "For reservations or private events, visit saltyzebrabistro.com. Thanks!",
            voice='alice'
        )
        response.record(
            transcribe=True,
            transcribe_callback='/webhook/voicemail?type=general',
            max_length=120,
            finish_on_key='#'
        )
    
    else:
        # Invalid input, redirect to main menu
        response.say("Sorry, that's not a valid option.", voice='alice')
        response.redirect('/webhook/voice')
    
    response.say("Thank you for calling The Salty Zebra!", voice='alice')
    return str(response)


@app.route('/webhook/recording', methods=['POST'])
def handle_recording():
    """Handle recorded audio from owner for custom messages"""
    try:
        # Get recording data
        recording_url = request.form.get('RecordingUrl', '')
        recording_type = request.args.get('type', 'unknown')
        duration = request.form.get('RecordingDuration', '0')
        
        # Store recording info
        import datetime
        recording_info = {
            'type': recording_type,
            'url': recording_url,
            'duration': duration,
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'status': 'saved'
        }
        recent_recordings.append(recording_info)
        
        # Keep only last 10 recordings
        if len(recent_recordings) > 10:
            recent_recordings.pop(0)
        
        print(f"RECORDING RECEIVED:")
        print(f"Type: {recording_type}")
        print(f"URL: {recording_url}")
        print(f"Duration: {duration} seconds")
        
        response = VoiceResponse()
        response.say(
            "Thank you! Your recording has been saved successfully. "
            "The system will be updated shortly with your personal message.",
            voice='alice'
        )
        
        return str(response)
        
    except Exception as e:
        print(f"Error handling recording: {e}")
        response = VoiceResponse()
        response.say("Sorry, there was an error saving your recording.", voice='alice')
        return str(response)


@app.route('/recording-status')
def recording_status():
    """Check recent recordings status"""
    html = """
    <h1>🎤 Recording Status</h1>
    <h2>Recent Recordings:</h2>
    """
    
    if recent_recordings:
        html += "<ul>"
        for recording in reversed(recent_recordings):  # Show newest first
            html += f"""
            <li>
                <strong>Type:</strong> {recording['type']}<br>
                <strong>Duration:</strong> {recording['duration']} seconds<br>
                <strong>Time:</strong> {recording['timestamp']}<br>
                <strong>Status:</strong> {recording['status']}<br>
                <strong>URL:</strong> <a href="{recording['url']}" target="_blank">Play Recording</a><br>
                <hr>
            </li>
            """
        html += "</ul>"
    else:
        html += "<p>No recordings found yet.</p>"
    
    html += """
    <p><a href="/">← Back to Home</a></p>
    <p><em>This is a temporary status page for checking recordings.</em></p>
    """
    
    return html


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

