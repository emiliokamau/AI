"""
Quick test script to verify SendGrid email delivery
Run this to test email before testing the full notification system
"""
import os
import requests

def test_sendgrid():
    api_key = os.environ.get('SENDGRID_API_KEY')
    from_email = os.environ.get('SENDGRID_FROM_EMAIL', 'emiliokamau35@gmail.com')
    from_name = os.environ.get('SENDGRID_FROM_NAME', 'Medical AI Assistant')
    
    if not api_key:
        print("❌ SENDGRID_API_KEY not set!")
        return False
    
    print(f"✓ API Key found: {api_key[:20]}...")
    print(f"✓ From Email: {from_email}")
    print(f"✓ From Name: {from_name}")
    print()
    
    # Test email
    to_email = input("Enter your email to receive test message: ").strip()
    if not to_email:
        to_email = from_email
        print(f"Using sender email: {to_email}")
    
    print(f"\nSending test email to {to_email}...")
    
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json'
    }
    
    data = {
        'personalizations': [{
            'to': [{'email': to_email}],
            'subject': 'Test Email from Medical AI Assistant'
        }],
        'from': {
            'email': from_email,
            'name': from_name
        },
        'content': [{
            'type': 'text/plain',
            'value': 'This is a test email to verify SendGrid integration is working correctly.\n\nIf you received this, your email notifications are configured properly!'
        }]
    }
    
    try:
        response = requests.post(
            'https://api.sendgrid.com/v3/mail/send',
            headers=headers,
            json=data,
            timeout=10
        )
        
        if response.status_code == 202:
            print("✅ Email sent successfully!")
            print(f"   SendGrid accepted the message (Status: {response.status_code})")
            print(f"   Check your inbox at: {to_email}")
            print("\n   Note: Delivery may take a few seconds to minutes.")
            return True
        else:
            print(f"❌ Failed to send email")
            print(f"   Status Code: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error sending email: {str(e)}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("SendGrid Email Test")
    print("=" * 60)
    print()
    test_sendgrid()
    print()
    print("=" * 60)
