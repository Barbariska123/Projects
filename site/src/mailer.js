import nodemailer from 'nodemailer';

function hasGmail() {
  return Boolean(process.env.GMAIL_USER && process.env.GMAIL_APP_PASSWORD)
}

function hasSMTP() {
  return Boolean(process.env.SMTP_HOST && process.env.SMTP_USER && process.env.SMTP_PASS)
}

export function isMailConfigured() {
  return hasSMTP() || hasGmail()
}

function buildTransportOptions() {
  if (hasSMTP()) {
    const secure = String(process.env.SMTP_SECURE || 'true').toLowerCase() === 'true'
    return {
      host: process.env.SMTP_HOST,
      port: Number(process.env.SMTP_PORT || (secure ? 465 : 587)),
      secure,
      auth: {
        user: process.env.SMTP_USER,
        pass: process.env.SMTP_PASS,
      },
    }
  }
  // Gmail fallback
  if (hasGmail()) {
    // Используем прямой SMTP для Gmail — стабильнее, чем service: 'gmail'
    return {
      host: 'smtp.gmail.com',
      port: 465,
      secure: true,
      auth: {
        user: process.env.GMAIL_USER,
        pass: process.env.GMAIL_APP_PASSWORD,
      },
    }
  }
  return null
}

export function getTransporter() {
  const opts = buildTransportOptions()
  if (!opts) return null
  return nodemailer.createTransport(opts)
}

export async function verifyMailer() {
  const t = getTransporter()
  if (!t) return false
  try { await t.verify(); return true } catch { return false }
}

export async function sendMail({ to, subject, html }) {
  const transporter = getTransporter();
  const from = process.env.MAIL_FROM || process.env.SMTP_USER || process.env.GMAIL_USER
  if (!transporter) {
    console.log('[DEV MAIL]', { to, subject, html });
    return 'dev-mail-noop';
  }
  const info = await transporter.sendMail({ from, to, subject, html });
  return info.messageId;
}
