package identitygen

import (
	"strings"
	"testing"
)

func TestPhotoTestPromptPrioritizesPhotographyAndFaceIdentity(t *testing.T) {
	p := Persona{Name: "Celeste Vale", Age: 32, Fictional: true}
	p.Physical.HairColor = "dark brown"
	p.Physical.EyeColor = "hazel-brown"
	p.Physical.SkinTone = "warm olive"
	p.Hobbies = []string{"jazz collecting"}
	p.AdultInterest.Cue = "barefoot interiors"
	p.IdentityReference.BodyPrompt = "very long legs"
	got := promptFor(p, Request{Style: "photo-test", Scene: "gray background"})
	if !strings.HasPrefix(got, "RAW portrait photograph") {
		t.Fatalf("photography must come first: %s", got)
	}
	for _, want := range []string{"age 32", "dark brown hair", "hazel-brown eyes", "warm olive skin", "gray background"} {
		if !strings.Contains(got, want) {
			t.Errorf("missing %q: %s", want, got)
		}
	}
	for _, unwanted := range []string{"jazz collecting", "barefoot interiors", "very long legs"} {
		if strings.Contains(got, unwanted) {
			t.Errorf("portrait test contains unrelated cue %q", unwanted)
		}
	}
}

func TestDefaultNegativeRejectsIllustration(t *testing.T) {
	for _, want := range []string{"cartoon", "anime", "illustration", "digital painting"} {
		if !strings.Contains(defaultNegative, want) {
			t.Errorf("missing %q", want)
		}
	}
}
