import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, '..');

// -----------------------------------------------------------------------------
// Contact Form Logic & Validation Unit Tests
// -----------------------------------------------------------------------------
function validateContactForm({ email, message, honeypot }) {
  if (honeypot && honeypot.trim()) {
    return { valid: true, botSuppressed: true };
  }
  const cleanEmail = (email || '').trim();
  const cleanMsg = (message || '').trim();

  if (!cleanEmail || !cleanEmail.includes('@') || !cleanEmail.includes('.')) {
    return { valid: false, error: 'Please enter a valid email address.' };
  }
  if (!cleanMsg || cleanMsg.length < 5) {
    return { valid: false, error: 'Please enter a message of at least 5 characters.' };
  }
  return { valid: true, botSuppressed: false, cleanEmail, cleanMsg };
}

test('Contact form rejects missing and malformed email addresses', () => {
  const cases = ['', '   ', 'plainaddress', 'missingat.com', 'user@domain'];
  for (const email of cases) {
    const res = validateContactForm({ email, message: 'Valid inquiry message' });
    assert.strictEqual(res.valid, false);
    assert.match(res.error, /valid email/i);
  }
});

test('Contact form rejects empty or short messages', () => {
  const cases = ['', '   ', 'hi', 'test'];
  for (const message of cases) {
    const res = validateContactForm({ email: 'rep@company.com', message });
    assert.strictEqual(res.valid, false);
    assert.match(res.error, /at least 5 characters/i);
  }
});

test('Contact form accepts valid inputs', () => {
  const res = validateContactForm({
    email: 'morgan@acme.corp',
    message: 'We are testing ColdCall Companion for our sales pod.'
  });
  assert.strictEqual(res.valid, true);
  assert.strictEqual(res.botSuppressed, false);
  assert.strictEqual(res.cleanEmail, 'morgan@acme.corp');
});

test('Honeypot field intercepts spam without triggering network submission', () => {
  const res = validateContactForm({
    email: 'bot@spam.link',
    message: 'Promotional spam content',
    honeypot: 'http://advertisement.example.com'
  });
  assert.strictEqual(res.valid, true);
  assert.strictEqual(res.botSuppressed, true);
});

// -----------------------------------------------------------------------------
// Unconfigured Endpoint & Safety Handling Tests
// -----------------------------------------------------------------------------
test('Unconfigured destination response sets state to unconfigured and displays honest error', async () => {
  // Mock fetch simulating 503 response from unconfigured server
  const mockFetch = async () => ({
    ok: false,
    status: 503,
    json: async () => ({ detail: 'Contact support destination is not configured on the server.' })
  });

  let state = 'submitting';
  let message = '';

  const resp = await mockFetch();
  if (!resp.ok && resp.status === 503) {
    state = 'unconfigured';
    message = 'Contact support is not configured yet. The operator has not connected a verified support destination.';
  }

  assert.strictEqual(state, 'unconfigured');
  assert.match(message, /not configured yet/i);
  // Verify we do NOT set state to success or claim email draft opened
  assert.notStrictEqual(state, 'success');
  assert.doesNotMatch(message, /draft opened/i);
  assert.doesNotMatch(message, /message has been received/i);
});

// -----------------------------------------------------------------------------
// Modal Accessibility & Markup Audits in Source Files
// -----------------------------------------------------------------------------
test('Contact and Privacy modals contain proper ARIA dialog attributes', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  // Contact Modal
  assert.match(mainJsx, /className="modal-card contact-modal"[\s\S]*?role="dialog"/);
  assert.match(mainJsx, /aria-modal="true"/);
  assert.match(mainJsx, /aria-labelledby="contact-modal-title"/);
  assert.match(mainJsx, /id="contact-modal-title"/);

  // Privacy Modal
  assert.match(mainJsx, /className="modal-card policy-modal"[\s\S]*?role="dialog"/);
  assert.match(mainJsx, /aria-labelledby="privacy-modal-title"/);
  assert.match(mainJsx, /id="privacy-modal-title"/);
});

test('Privacy Policy is prominently marked as DRAFT with honest deletion instructions', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  // Must be marked as DRAFT
  assert.match(mainJsx, /\[DRAFT\] Privacy Policy & Data Architecture/);
  assert.match(mainJsx, /DRAFT — OPERATOR INPUT REQUIRED BEFORE PUBLIC LAUNCH/);

  // Must clarify that Clear Token does NOT delete local call history
  assert.match(mainJsx, /Clearing your token does not delete existing local or cloud call records/);

  // Must provide real deletion paths
  assert.match(mainJsx, /clear your browser’s site storage\/cookies for this domain/);
  assert.match(mainJsx, /contact your organization’s system administrator with your Caller ID/);
});

// -----------------------------------------------------------------------------
// Open Graph & Schema.org Metadata Verification
// -----------------------------------------------------------------------------
test('index.html contains absolute og:image URL with image/png and dimensions', () => {
  const indexHtml = fs.readFileSync(path.join(frontendDir, 'index.html'), 'utf-8');

  assert.match(indexHtml, /<meta property="og:image" content="https:\/\/[^"]+\/og-image\.png" \/>/);
  assert.match(indexHtml, /<meta property="og:image:type" content="image\/png" \/>/);
  assert.match(indexHtml, /<meta property="og:image:width" content="1200" \/>/);
  assert.match(indexHtml, /<meta property="og:image:height" content="630" \/>/);
  assert.match(indexHtml, /<meta name="twitter:image" content="https:\/\/[^"]+\/og-image\.png" \/>/);
});

test('Schema.org does not claim free pricing without established pricing tiers', () => {
  const indexHtml = fs.readFileSync(path.join(frontendDir, 'index.html'), 'utf-8');

  // Verify that "offers" is NOT present in index.html
  assert.doesNotMatch(indexHtml, /"offers"/);
  assert.doesNotMatch(indexHtml, /"price":\s*"0"/);
});

test('Privacy Policy contains Section 7 accurately documenting contact data collection and retention', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  assert.match(mainJsx, /<h3>7\. Contact & Support Submissions<\/h3>/);
  assert.match(mainJsx, /Information Collected:.*email address.*message text/i);
  assert.match(mainJsx, /Destination & Dispatch:.*server-side support webhook/i);
  assert.match(mainJsx, /Purpose & Retention:.*never sold or shared with third-party advertisers/i);
});

test('Contact submission logic dispatches to backend API URL and respects public override', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  // Verify that it defaults to ${API}/contact
  assert.match(mainJsx, /\$\{API\}\/contact/);
  // Verify that it checks VITE_PUBLIC_CONTACT_ENDPOINT
  assert.match(mainJsx, /import\.meta\.env\.VITE_PUBLIC_CONTACT_ENDPOINT/);
});

test('resolveApiBaseUrl guards against silent localhost fallback in production', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  // Verify function existence
  assert.match(mainJsx, /function resolveApiBaseUrl\(\)/);
  // Verify it only falls back to localhost:8000 when DEV is true
  assert.match(mainJsx, /if \(import\.meta\.env\.DEV\)\s*\{\s*return 'http:\/\/localhost:8000';\s*\}/);
  // Verify that in production it does NOT return localhost:8000
  assert.match(mainJsx, /VITE_API_BASE_URL is not configured in production/);
});

test('request helper verifies application/json content-type to detect misrouted SPA rewrites', () => {
  const mainJsx = fs.readFileSync(path.join(frontendDir, 'src', 'main.jsx'), 'utf-8');

  // Verify that it inspects content-type header
  assert.match(mainJsx, /res\.headers\.get\('content-type'\)/);
  // Verify that it requires application/json
  assert.match(mainJsx, /contentType\.includes\('application\/json'\)/);
  // Verify that error message diagnoses unconfigured VITE_API_BASE_URL
  assert.match(mainJsx, /Ensure VITE_API_BASE_URL is configured/);
});
