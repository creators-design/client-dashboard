# Social media analytics — all clients

A website that shows Instagram and YouTube growth for every client and refreshes itself every morning.

- `index.html` — the dashboard (Overview, Client growth, Instagram, YouTube, All content).
- `data.json` — the numbers. Replaced automatically every day.
- `fetch_data.py` — pulls the latest numbers from Windsor.ai.
- `.github/workflows/daily-update.yml` — runs `fetch_data.py` every day at 07:00 IST.

## One-time setup (about 15 minutes, free)

1. **Get your Windsor.ai API key.** Log in at https://onboard.windsor.ai and copy your API key.
2. **Create a GitHub repository.** Sign in at https://github.com (create a free account if needed) → **New repository** → name it e.g. `client-dashboard` → **Public** → **Create repository**.
3. **Upload these files.** On the new repository page click **uploading an existing file**, drag in everything from this folder (including the `.github` folder), then **Commit changes**.
   - If your browser hides the `.github` folder, create it by hand: **Add file → Create new file**, type `.github/workflows/daily-update.yml` as the name, paste the contents of that file, **Commit**.
4. **Add the API key as a secret.** Repository **Settings → Secrets and variables → Actions → New repository secret**. Name: `WINDSOR_API_KEY`. Value: your key. **Add secret**.
5. **Turn on the website.** **Settings → Pages** → Source: **Deploy from a branch** → Branch: `main`, folder `/ (root)` → **Save**. After a minute the page shows your link, e.g. `https://yourname.github.io/client-dashboard/`.
6. **Run the first refresh.** **Actions** tab → **Daily data refresh** → **Run workflow**. When it turns green (a few minutes), reload the website: the "Updated" date at the top shows today.

From then on it refreshes itself every morning. Send your founder the link.

## Good to know

- **Who can see it:** anyone with the link. Your Windsor.ai key stays secret inside GitHub and is never in the website.
- **If a refresh fails:** GitHub emails you, and the site keeps showing the last good numbers. Open **Actions → the failed run** to see why (usually an expired connection in Windsor.ai — reconnect it there).
- **Adding a client:** connect their account in Windsor.ai, then add the Instagram username or YouTube channel name at the top of `fetch_data.py`, and ask Claude to add them to the dashboard's client lists in `index.html`.
- **Data timing:** Instagram runs through yesterday; YouTube analytics arrive about two days late. Thumbnail click-through rate isn't available through Windsor.ai, so average % viewed is shown instead.
