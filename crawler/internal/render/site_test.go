package render

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSiteFromRepo(t *testing.T) {
	site := SiteFromRepo("Owner/my-repo")
	if site.URL != "https://owner.github.io/my-repo/" || site.Owner() != "Owner" || site.Host() != "https://owner.github.io" {
		t.Fatalf("unexpected site %+v host=%s", site, site.Host())
	}
}

func TestCurrentSiteEnv(t *testing.T) {
	t.Setenv("VIETLOTT_REPO", "acme/lotto")
	t.Setenv("VIETLOTT_SITE_URL", "https://lotto.example.com")
	t.Setenv("VIETLOTT_GA_ID", "G-TEST123")
	site := CurrentSite()
	if site.Repo != "acme/lotto" || site.URL != "https://lotto.example.com/" || site.GAID != "G-TEST123" {
		t.Fatalf("unexpected site %+v", site)
	}
	t.Setenv("VIETLOTT_REPO", "")
	t.Setenv("VIETLOTT_SITE_URL", "")
	if got := CurrentSite(); got.Repo != DefaultRepo || got.URL != SiteFromRepo(DefaultRepo).URL {
		t.Fatalf("default site = %+v", got)
	}
}

const sampleHTML = `<meta name="author" content="hieptd-ai" />
<link rel="canonical" href="https://hieptd-ai.github.io/vietlott-predict/en/" />
"identifier": "https://github.com/hieptd-ai/vietlott-predict",
"creator": { "@type": "Person", "name": "vietvudanh", "url": "https://github.com/vietvudanh" },
"publisher": { "@type": "Person", "name": "hieptd-ai", "url": "https://github.com/hieptd-ai" },
"contentUrl": "https://raw.githubusercontent.com/hieptd-ai/vietlott-predict/main/data/power655.jsonl"
[upstream issue #13](https://github.com/vietvudanh/vietlott-data/issues/13), fork of https://github.com/vietvudanh/vietlott-data
# (https://hieptd-ai.github.io/vietlott-predict) at https://hieptd-ai.github.io/robots.txt
    <!-- Google tag (gtag.js) -->
    <script
        async
        src="https://www.googletagmanager.com/gtag/js?id=G-BQHSD144BE"
    ></script>
    <script>
        window.dataLayer = window.dataLayer || [];
        gtag("config", "G-BQHSD144BE");
    </script>
<body>`

func TestApplyRewritesSiteURLs(t *testing.T) {
	site := Site{URL: "https://acme.github.io/lotto/", Repo: "acme/lotto"}
	out := site.Apply(sampleHTML)
	for _, want := range []string{
		`<meta name="author" content="acme" />`,
		`href="https://acme.github.io/lotto/en/"`,
		`"identifier": "https://github.com/acme/lotto"`,
		`"creator": { "@type": "Person", "name": "vietvudanh", "url": "https://github.com/vietvudanh" }`,
		`"publisher": { "@type": "Person", "name": "acme", "url": "https://github.com/acme" }`,
		`https://raw.githubusercontent.com/acme/lotto/main/data/power655.jsonl`,
		`https://github.com/vietvudanh/vietlott-data/issues/13), fork of https://github.com/vietvudanh/vietlott-data`,
		`(https://acme.github.io/lotto) at https://acme.github.io/robots.txt`,
	} {
		if !strings.Contains(out, want) {
			t.Errorf("missing %q in:\n%s", want, out)
		}
	}
	for _, gone := range []string{"hieptd-ai", "googletagmanager", "G-BQHSD144BE"} {
		if strings.Contains(out, gone) {
			t.Errorf("%q should be removed:\n%s", gone, out)
		}
	}
	if again := site.Apply(out); again != out {
		t.Errorf("Apply is not idempotent")
	}
}

func TestApplyDefaultSiteOnlyDropsAnalytics(t *testing.T) {
	out := SiteFromRepo(DefaultRepo).Apply(sampleHTML)
	if strings.Contains(out, "googletagmanager") {
		t.Fatalf("analytics tag should be dropped:\n%s", out)
	}
	if !strings.Contains(out, `href="https://hieptd-ai.github.io/vietlott-predict/en/"`) || !strings.Contains(out, "fork of https://github.com/vietvudanh/vietlott-data") {
		t.Fatalf("default site content changed:\n%s", out)
	}
}

func TestApplyKeepsAnalyticsWhenConfigured(t *testing.T) {
	site := Site{URL: "https://acme.github.io/lotto/", Repo: "acme/lotto", GAID: "G-ACME1"}
	out := site.Apply(sampleHTML)
	if !strings.Contains(out, "gtag/js?id=G-ACME1") || !strings.Contains(out, `gtag("config", "G-ACME1")`) {
		t.Fatalf("analytics id not substituted:\n%s", out)
	}
}

func TestApplyMigratesDefaultForkSite(t *testing.T) {
	def := SiteFromRepo(DefaultRepo)
	site := Site{URL: "https://lotto.example.com/", Repo: "acme/lotto"}
	out := site.Apply(`<link href="` + def.URL + `x/" /> https://github.com/` + DefaultRepo + ` https://github.com/vietvudanh/vietlott-data`)
	if out != `<link href="https://lotto.example.com/x/" /> https://github.com/acme/lotto https://github.com/vietvudanh/vietlott-data` {
		t.Fatalf("got %q", out)
	}
}

func TestApplyToStaticFiles(t *testing.T) {
	root := t.TempDir()
	if err := os.MkdirAll(filepath.Join(root, "docs"), 0o755); err != nil {
		t.Fatal(err)
	}
	robots := filepath.Join(root, "docs", "robots.txt")
	if err := os.WriteFile(robots, []byte("Sitemap: https://hieptd-ai.github.io/vietlott-predict/sitemap.xml\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := (Site{URL: "https://acme.github.io/lotto/", Repo: "acme/lotto"}).ApplyToStaticFiles(root); err != nil {
		t.Fatal(err)
	}
	raw, _ := os.ReadFile(robots)
	if string(raw) != "Sitemap: https://acme.github.io/lotto/sitemap.xml\n" {
		t.Fatalf("robots.txt = %q", raw)
	}
}
