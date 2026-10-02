package termui

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"
)

type Spinner struct {
	label string
	stop  chan struct{}
	done  chan struct{}
	once  sync.Once
	tty   bool
}

func Enabled() bool {
	if os.Getenv("NO_COLOR") != "" || os.Getenv("CI") != "" || os.Getenv("TERM") == "dumb" {
		return false
	}
	fi, err := os.Stderr.Stat()
	return err == nil && (fi.Mode()&os.ModeCharDevice) != 0
}

func Start(label string) *Spinner {
	s := &Spinner{label: label, stop: make(chan struct{}), done: make(chan struct{}), tty: Enabled()}
	if !s.tty {
		fmt.Fprintf(os.Stderr, "▶ %s\n", label)
		close(s.done)
		return s
	}
	go s.loop()
	return s
}

func (s *Spinner) loop() {
	defer close(s.done)
	frames := []string{"▰▱▱▱▱▱▱▱", "▰▰▱▱▱▱▱▱", "▰▰▰▱▱▱▱▱", "▰▰▰▰▱▱▱▱", "▰▰▰▰▰▱▱▱", "▰▰▰▰▰▰▱▱", "▰▰▰▰▰▰▰▱", "▰▰▰▰▰▰▰▰"}
	colors := []string{"\x1b[38;5;45m", "\x1b[38;5;51m", "\x1b[38;5;87m", "\x1b[38;5;123m", "\x1b[38;5;159m", "\x1b[38;5;201m"}
	reset := "\x1b[0m"
	start := time.Now()
	t := time.NewTicker(110 * time.Millisecond)
	defer t.Stop()
	i := 0
	for {
		select {
		case <-s.stop:
			fmt.Fprint(os.Stderr, "\r\x1b[2K")
			return
		case <-t.C:
			elapsed := time.Since(start).Round(time.Second)
			bar := frames[i%len(frames)]
			color := colors[i%len(colors)]
			fmt.Fprintf(os.Stderr, "\r\x1b[2K%s%s%s  %s  %s", color, bar, reset, s.label, elapsed)
			i++
		}
	}
}

func (s *Spinner) Stop(ok bool) {
	s.once.Do(func() {
		if s.tty {
			close(s.stop)
			<-s.done
		}
		icon, color := "✓", "\x1b[38;5;82m"
		if !ok {
			icon, color = "✗", "\x1b[38;5;196m"
		}
		if s.tty {
			fmt.Fprintf(os.Stderr, "%s%s\x1b[0m %s\n", color, icon, s.label)
		}
	})
}

func Label(args ...string) string {
	return strings.TrimSpace(strings.Join(args, " "))
}
