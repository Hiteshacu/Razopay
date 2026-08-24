const scenarioData = {
  receipt: {
    label: "Receipt-first trust",
    title: "A merchant receives a shared payment screenshot and wants instant authenticity.",
    text:
      "The signed receipt keeps its proof inside the image itself, so even after forwarding the merchant can verify that the bank-generated payment confirmation was not edited.",
    points: [
      "Invisible watermark travels with the screenshot.",
      "Perceptual fingerprint tolerates moderate compression noise.",
      "Result can return authentic, fake, or tampered.",
    ],
    chip: "Trust + Security",
    trust: 92,
    security: 94,
    accessibility: 78,
  },
  statement: {
    label: "Document trust",
    title: "A rural customer shares a banking statement PDF for loan, subsidy, or grievance processing.",
    text:
      "The PDF path signs each page independently, so branch staff can verify a multi-page document and pinpoint exactly which page is authentic or altered.",
    points: [
      "Each page carries its own hidden trust bundle.",
      "Verification returns page-by-page results.",
      "Useful for statements, sanction letters, and claim forms.",
    ],
    chip: "Security + Accessibility",
    trust: 86,
    security: 96,
    accessibility: 83,
  },
  field: {
    label: "Field-agent assurance",
    title: "A BC agent or CSP operator checks a forwarded receipt in a low-connectivity environment.",
    text:
      "Because verification relies on the public key and embedded proof, the trust flow can be packaged into lightweight field tools that reduce dependence on fragile metadata or server lookups.",
    points: [
      "Simple verdicts help non-technical operators act quickly.",
      "Public-key verification supports offline-friendly workflows.",
      "Audit logs support dispute resolution and accountability.",
    ],
    chip: "Trust + Accessibility",
    trust: 90,
    security: 82,
    accessibility: 95,
  },
};

const buttons = Array.from(document.querySelectorAll(".scenario-button"));
const label = document.getElementById("scenario-label");
const title = document.getElementById("scenario-title");
const text = document.getElementById("scenario-text");
const points = document.getElementById("scenario-points");
const chip = document.getElementById("scenario-chip");
const trustMeter = document.getElementById("meter-trust");
const securityMeter = document.getElementById("meter-security");
const accessibilityMeter = document.getElementById("meter-accessibility");

function renderScenario(key) {
  const scenario = scenarioData[key];
  if (!scenario) {
    return;
  }

  label.textContent = scenario.label;
  title.textContent = scenario.title;
  text.textContent = scenario.text;
  chip.textContent = scenario.chip;
  points.innerHTML = scenario.points.map((item) => `<li>${item}</li>`).join("");
  trustMeter.style.width = `${scenario.trust}%`;
  securityMeter.style.width = `${scenario.security}%`;
  accessibilityMeter.style.width = `${scenario.accessibility}%`;

  buttons.forEach((button) => {
    const isActive = button.dataset.scenario === key;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", String(isActive));
  });
}

buttons.forEach((button) => {
  button.addEventListener("click", () => renderScenario(button.dataset.scenario));
});

const revealObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      }
    });
  },
  {
    threshold: 0.12,
  },
);

document.querySelectorAll(".reveal").forEach((element) => {
  revealObserver.observe(element);
});

renderScenario("receipt");
