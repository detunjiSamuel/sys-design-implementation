const shortenBtn = document.getElementById("shortenBtn");
const urlInput = document.getElementById("urlInput");
const resultDiv = document.getElementById("result");
const shortUrlLink = document.getElementById("shortUrl");
const copyBtn = document.getElementById("copyBtn");

const API_BASE = "/api";

shortenBtn.addEventListener("click", async () => {
  const longUrl = urlInput.value.trim();
  if (!longUrl) return alert("Please enter a URL!");

  try {
    const res = await fetch(`${API_BASE}/shorten`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: longUrl }),
    });

    if (!res.ok) throw new Error("Failed to shorten URL");

    const data = await res.json();
    shortUrlLink.href = data.short_url;
    shortUrlLink.textContent = data.short_url;

    resultDiv.classList.remove("hidden");
  } catch (err) {
    alert("Error: " + err.message);
  }
});

copyBtn.addEventListener("click", async () => {
  await navigator.clipboard.writeText(shortUrlLink.href);
  copyBtn.textContent = "Copied!";
  setTimeout(() => (copyBtn.textContent = "Copy"), 1500);
});
