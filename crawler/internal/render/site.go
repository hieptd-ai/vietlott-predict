package render

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
)

// The page templates use this repository's URLs (DefaultRepo). Every rendered file is passed
// through Site.Apply, which rewrites them (canonical links, hreflang, Open Graph, JSON-LD,
// sitemap, raw data downloads) to the site configured by VIETLOTT_REPO / VIETLOTT_SITE_URL,
// e.g. after a rename, a fork or a move to a custom domain. Links to the upstream project
// (attribution, upstream issues, the data-sync source) are left untouched.

// DefaultRepo is the GitHub repository ("owner/name") this project publishes from.
const DefaultRepo = "hieptd-ai/vietlott-predict"

// Site describes where the rendered pages are published.
type Site struct {
	// URL is the absolute site root with a trailing slash, e.g. https://owner.github.io/repo/.
	URL string
	// Repo is the GitHub repository as "owner/name".
	Repo string
	// GAID is an optional Google Analytics measurement id (G-XXXX); empty removes the tag.
	GAID string
}

// Owner returns the repository owner.
func (s Site) Owner() string {
	owner, _, _ := strings.Cut(s.Repo, "/")
	return owner
}

// Host returns the site's scheme and host, e.g. https://owner.github.io.
func (s Site) Host() string {
	rest := strings.TrimPrefix(strings.TrimPrefix(s.URL, "https://"), "http://")
	host, _, _ := strings.Cut(rest, "/")
	scheme := "https://"
	if strings.HasPrefix(s.URL, "http://") {
		scheme = "http://"
	}
	return scheme + host
}

// SiteFromRepo derives the default GitHub Pages URL for a repository.
func SiteFromRepo(repo string) Site {
	owner, name, _ := strings.Cut(repo, "/")
	return Site{URL: "https://" + strings.ToLower(owner) + ".github.io/" + name + "/", Repo: repo}
}

// CurrentSite reads VIETLOTT_REPO, VIETLOTT_SITE_URL and VIETLOTT_GA_ID, falling back to
// DefaultRepo and its GitHub Pages URL.
func CurrentSite() Site {
	repo := strings.TrimSpace(os.Getenv("VIETLOTT_REPO"))
	if !strings.Contains(repo, "/") {
		repo = DefaultRepo
	}
	site := SiteFromRepo(repo)
	if url := strings.TrimSpace(os.Getenv("VIETLOTT_SITE_URL")); url != "" {
		site.URL = strings.TrimRight(url, "/") + "/"
	}
	site.GAID = strings.TrimSpace(os.Getenv("VIETLOTT_GA_ID"))
	return site
}

var gtagBlock = regexp.MustCompile(`(?s)\n?[ \t]*<!-- Google tag \(gtag\.js\) -->\s*<script[^>]*googletagmanager\.com/gtag/js\?id=[A-Z0-9-]+"[^>]*>\s*</script>\s*<script>.*?gtag\("config", "[A-Z0-9-]+"\);\s*</script>`)

// Apply rewrites the DefaultRepo site URLs in content to this site and renders (or drops) the
// Google Analytics tag.
func (s Site) Apply(content string) string {
	if from := SiteFromRepo(DefaultRepo); from.Repo != s.Repo || from.URL != s.URL {
		pairs := []string{
			from.URL, s.URL,
			strings.TrimSuffix(from.URL, "/"), strings.TrimSuffix(s.URL, "/"),
			from.Host() + "/robots.txt", s.Host() + "/robots.txt",
			"https://raw.githubusercontent.com/" + from.Repo + "/", "https://raw.githubusercontent.com/" + s.Repo + "/",
			"github.com/" + from.Repo, "github.com/" + s.Repo,
			`"publisher": { "@type": "Person", "name": "` + from.Owner() + `", "url": "https://github.com/` + from.Owner() + `" }`,
			`"publisher": { "@type": "Person", "name": "` + s.Owner() + `", "url": "https://github.com/` + s.Owner() + `" }`,
			`<meta name="author" content="` + from.Owner() + `" />`, `<meta name="author" content="` + s.Owner() + `" />`,
			strings.TrimPrefix(from.Host(), "https://"), strings.TrimPrefix(s.Host(), "https://"),
		}
		content = strings.NewReplacer(pairs...).Replace(content)
	}

	content = gtagBlock.ReplaceAllStringFunc(content, func(block string) string {
		if s.GAID == "" {
			return ""
		}
		return regexp.MustCompile(`G-[A-Z0-9]+`).ReplaceAllString(block, s.GAID)
	})
	return content
}

// staticSiteFiles are hand-written files (not produced by a renderer) that still carry site URLs.
var staticSiteFiles = []string{
	"index.html",
	filepath.Join("docs", "robots.txt"),
	filepath.Join("docs", "llms.txt"),
	filepath.Join("docs", "analysis", "index.html"),
}

// ApplyToStaticFiles rewrites site URLs inside the hand-written static files under root.
func (s Site) ApplyToStaticFiles(root string) error {
	for _, rel := range staticSiteFiles {
		path := filepath.Join(root, rel)
		raw, err := os.ReadFile(path)
		if os.IsNotExist(err) {
			continue
		}
		if err != nil {
			return err
		}
		if updated := s.Apply(string(raw)); updated != string(raw) {
			if err := os.WriteFile(path, []byte(updated), 0o644); err != nil {
				return err
			}
		}
	}
	return nil
}
