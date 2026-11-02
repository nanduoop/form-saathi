# Task 11: voice-first Saathi app with a real visual design

The current page is a developer console. Build the real product: a voice-first, mobile-first app that a first-time smartphone user in a village can use without reading English. Keep the console for judges.

## Routing
- Move the current app/static/index.html to app/static/console.html, served at GET /console (unchanged behaviour).
- GET / serves the new app: app/static/app.html (+ app/static/app.css, app/static/app.js, app/static/art/). No build step, no framework, plain JS.

## The experience (one step per screen, Saathi talks first)
Saathi is a friendly helper voice. Every screen speaks its main line automatically (browser speechSynthesis with the language voice: hi-IN, kn-IN, mr-IN, te-IN, ta-IN, bn-IN, en-IN), shows the same line as large text, and has a big round mic button. A speaker toggle in the corner mutes/unmutes. If no voice exists for the language, show the text and a small note; never fail.
1. Language: 7 big buttons in native script (हिंदी, ಕನ್ನಡ, मराठी, తెలుగు, தமிழ், বাংলা, English). Saathi greets immediately in that language.
2. "What do you need help with?" Tap a big illustrated tile (Scholarship for studies, PM-KISAN for farmers, Crop insurance, Not sure) OR tap the mic and say it. Spoken goal is recorded (MediaRecorder) and sent as the "goal" (transcribe via a new POST /transcribe endpoint that uses muse-voice-transcribe-1.0 and returns {text}). Show "I heard: <text>" with Yes / Say again.
3. "Show me your documents": big "Take photo" button (input type=file accept=image/* capture=environment, multiple), thumbnails of taken photos, and "Use a sample family" (Sample A/B/C as three small chips). Then Start.
4. Working: a calm animated progress view. Show and SPEAK the record.progress lines as they arrive (speak each new line once, short). Five-step progress bar with icons: Photos, Your details, Schemes, Form, Plan.
5. Photo help (needs_photo): show the photo with the SAM box drawn on it (canvas overlay) and the advice spoken; Retake / Use sample retake.
6. Question (needs_input): full-screen question card, auto-spoken, huge mic button (tap to start, tap to stop; show a live level meter and a timer), "Type instead" link. After recording show "I heard: ..." from the transcript before sending, with Send / Say again.
7. Warning: discrepancies (e.g. Patel vs Patil) as a clear amber card with an icon, spoken, explaining what to get corrected and where.
8. Result: big outcome ("You can apply for Post-Matric Scholarship" / "Not eligible because ..."), the plan as numbered illustrated step cards, each with a play button to hear it; closed deadlines visibly marked. Buttons: "Download documents for upload" (pack.zip, with sizes), "See the filled form", "I confirm these details are true". A small "See the proof" link opens /console?case=<id> (make the console accept ?case= to load an existing case).
Back button on every step; state kept in sessionStorage so a refresh resumes the case.

## Visual design
- Feel: warm, trustworthy, Indian, not a dashboard. Palette as CSS variables: ink #1d2433, paper #fbf7f0 (explicit body background, light theme only, set color-scheme: light), primary deep teal #0f5e63, accent marigold #f2a516, success #2e7d32, warning amber #b26a00 on #fff4dc, danger #b3261e.
- Type: Google Fonts "Noto Sans" plus the script fonts (Noto Sans Devanagari, Kannada, Telugu, Tamil, Bengali). Base 18px, headings 26-30px, line-height 1.5.
- Layout: mobile first (360px wide works with no horizontal scroll), max width 520px centred on desktop, cards with 16px radius and soft shadow, touch targets at least 56px, mic button 96px with a pulsing ring while listening.
- Icons: inline SVG only. Illustrations: generate them with Meta's image model (see below); fall back to simple inline SVG if generation fails.
- All fixed UI text comes from one dictionary in app.js for the 7 languages (English fallback). No raw codes or field ids on screen; use status_label, stage_label and field labels from the API.

## Art with Muse Image
Write scripts/make_art.py that calls muse-image-1.0 through the existing Meta client to create 6 flat, friendly illustrations in one consistent style (a young Indian student with documents; a farmer in a field; a crop with an umbrella for insurance; a phone taking a photo of a document; a helper character 'Saathi' waving; a checklist with a green tick). Try client.images.generate(model="muse-image-1.0", prompt=..., size="1024x1024") first; if that endpoint fails, try client.images.edit with a plain off-white starter image. Save as app/static/art/<name>.png resized to 512px and compressed under 120 KB each, and commit them. Run it once.

## Acceptance
- python tests/test_offline.py still passes.
- python scripts/make_art.py produced the images (or the SVG fallback is in place and the report says why).
- Start the server; with Python requests: GET / returns app.html containing the language buttons, the mic button and the dictionary; GET /console returns the old console; POST /transcribe with samples/answer_hi.m4a (if it exists) returns text; drive Sample A through the API as in Task 10.
- If playwright is importable, take screenshots of every step at 390x844 into docs/screens/ and check there is no horizontal scroll; otherwise skip and say so.
- Update README: a "Voice-first app" section and screenshots if made.
Commit 'Task 11: voice-first Saathi app and visual design (built with Muse Code)'.
