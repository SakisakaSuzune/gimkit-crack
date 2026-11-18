# gimkit-crack

Local script +  LLM API to automatically answer Gimkit questions and build a question bank. The system reads questions and clicks on answer options via Chrome DevTools Protocol (CDP); it checks the local question bank for answers or calls the LLM API if not found.


## Environment Preparing

- Python 3
- Chrome / Chromium started with debug port
- LLM API-Key

## Installing

```bash
cd <path-to-your-repo>
git clone https://github.com/SakisakaSuzune/gimkit-crack
cd gimkit-crack
```

Create `.env.local` at ./

```text
BASE_URL=
API_KEY=
MODEL=
```

Environment Variable > `.env.local` > Default Value

To override with environment variables:

```bash
export API_KEY=sk-...
export BASE_URL=https://api.deepseek.com/chat/completions
```

## Running

1. Start the browser with debug mode:

macOS / Linux:

```bash
# (Chrome)
google-chrome --remote-debugging-port=9222
```

Windows：

```bat
"...\chrome.exe" --remote-debugging-port=9222
```

2. Join a Gimkit game，点击 **Start Game**。Ensure that `curl http://127.0.0.1:9222/json/list` returns a list containing the tab.

3. Run script：

```bash
python3 -u bot_v2.py 100
```
Replace 100 with the amount of questions you'd like to answer.
