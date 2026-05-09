# ENTROPY PRIME TEST AND IMPROVEMENT PLAN

This note is for Ganesh, Ved, and Vivek.

## 1) How to start the app

1. Open the project folder.
2. Run `start.bat` from the project root.
3. Wait until both services are ready.
4. Open the app in the browser at `http://localhost:3000`.
5. Backend API docs are at `http://localhost:8000/docs`.

If needed, the frontend is started with `npm run dev` and the backend with `python -m uvicorn main:app --port 8000 --reload`.

## 2) What to test

### Test 1: User typing pattern and re-authentication

- Let one user type normally for a few minutes.
- The app should learn and store the user's typing pattern.
- Then make the same user type very fast with random alphabets on purpose.
- This is wrong behavior.
- The app should detect the change and trigger a warning.
- The app should ask for re-authentication.

### Test 2: Continuous user monitoring

- When a user is logged in, the app should keep checking the typing pattern.
- If another person starts typing, the pattern should look different.
- After some time, the app should compare the current typing pattern with the saved user pattern.
- If the pattern does not match, the app should trigger re-authentication.
- This check should happen every time, not only once.

### Test 3: Honeypot testing with a bot

- Create a simple bot script in another terminal or another browser tab.
- Keep the real app running in one terminal/tab.
- The bot should send fake input and behave like an attacker.
- The app should detect the bot and trigger the honeypot.
- The honeypot should return random or synthetic data that looks like the real app.
- Verify that the bot does not get real sensitive data.

## 3) Division of work

### Ganesh

- Test the first login and typing sample collection.
- Check whether the baseline pattern is created correctly.
- Verify that wrong typing behavior triggers warning and re-auth.
- Write down the exact steps and results.

Ganesh, please focus on the first-user typing flow. Start the app, let one user type normally for a few minutes so the baseline pattern can be learned, and then test what happens when the same user deliberately types fast with random alphabets. The app should treat that as suspicious, show a warning, and ask for re-authentication. Please keep the steps simple, check whether the baseline is saved correctly, and note any place where the behavior is too weak, too slow, or not clear enough for a normal tester.

### Ved

- Test continuous monitoring while the user stays logged in.
- Check whether pattern drift is detected over time.
- Verify that a different person typing causes re-auth.
- Suggest improvements if the monitoring is too slow or too strict.

Ved, please focus on the continuous monitoring flow while a user stays logged in. The app should keep checking the current typing pattern against the stored user pattern, not just once but all the time. Test the case where another person starts typing and the pattern changes, then confirm the app notices the difference and triggers re-authentication. If the detection is too strict, too slow, or confusing, suggest a simple improvement that makes the system easier to trust and easier to test.

### Vivek

- Build and run the bot script for honeypot testing.
- Keep the app running in a separate terminal/tab.
- Verify that the honeypot is triggered for bot-like behavior.
- Check that the returned data is fake and safe.

Vivek, please focus on the honeypot and bot test. Run the real app in one terminal or tab and run a simple bot script in another terminal or tab to imitate suspicious behavior. The app should detect the bot-like activity, trigger the honeypot, and return fake or safe data instead of real sensitive data. Please verify that the honeypot behaves like the app from the outside, but does not leak anything important, and record any change needed to make the bot test more reliable.

## 4) What to improve after testing

- Make the typing pattern detection more reliable.
- Make re-authentication happen faster when behavior changes.
- Make the honeypot trigger clearly and consistently.
- Add simple logs so we can see why the app made each decision.
- Keep the system easy to test again later.

## 5) Final goal

Build a full system design where:

- normal users are learned correctly,
- suspicious typing is detected quickly,
- re-authentication happens when the pattern changes,
- bots are trapped in the honeypot,
- and the app stays active all the time while monitoring the user.