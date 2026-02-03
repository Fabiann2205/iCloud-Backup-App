# iCloud Backup App - Documentation

This app automatically uploads Home Assistant backups to your iCloud Drive.

## Important information if you use Apple Advanced Data Protection

If you have Apple Advanced Data Protection enabled, third-party apps (like this app) cannot access your iCloud Drive without your permission. 
Everytime the app tries to connect, you will receive a notification on your Apple devices asking for permission to access your data on iCloud.
You must **allow** this access for the app to work properly.

Currently, there is no way to pre-approve this access, so you will need to approve it each time the app connects to iCloud (e.g., everytime it tries to upload a backup after a short time).

## 📋 Configuration

### Step 1: Install the app
1. Add this repository to your app repositories
2. Install the "iCloud Backup" app
3. **Do NOT start the app yet!**

### Step 2: Fill in the configuration
Open the configuration and fill in the following fields:

```yaml
username: "your-icloud-email-address"
password: "your-icloud-password"
folder: "HomeAssistant-Backups"
delete_after_upload: false
```

#### Configuration options:

| Option | Description | Example |
|--------|-------------|----------|
| `username` | Your Apple ID (iCloud email) | `max@icloud.com` |
| `password` | Your regular iCloud password | `YourPassword123` |
| `folder` | Name of the iCloud Drive folder | `HomeAssistant-Backups` |
| `delete_after_upload` | Delete local backups after upload | `true` or `false` |

### Use Secrets

To avoid putting your username and password directly into the app configuration, you can use [Secrets](https://www.home-assistant.io/docs/configuration/secrets/).


### Step 3: Start the app
1. Save the configuration
2. Start the app
3. **If 2FA is enabled:** Open the Web UI and enter the code (see below)

---

## 🔐 Two-Factor Authentication (2FA)

### How does 2FA work?

If your iCloud account has 2FA enabled (recommended!), you must enter a verification code on the first start. You use your **regular iCloud password** together with the 2FA verification.

### Flow:

1. **app starts** → Connects to iCloud
2. **2FA is detected** → app waits for a code
3. **You receive a push notification** on your iPhone/iPad/Mac
4. **A code appears** (e.g., `123456`)
5. **Open the app's Web UI** (button in the app overview)
6. **Enter the 6-digit code** and click "Submit"
7. **Authentication successful** → The app will now run automatically

⚠️ If you change your password or after a long period of inactivity, 2FA may be required again.

### Open the Web UI:

Use the **"OPEN WEB UI"** button in the app overview
