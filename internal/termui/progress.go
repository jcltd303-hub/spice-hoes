package termui

import (
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"
)

type Spinner struct {
	label   string
	status  string
	percent float64
	metrics map[string]string
	started time.Time
	stop    chan struct{}
	done    chan struct{}
	once    sync.Once
	mu      sync.RWMutex
	tty     bool
}

func Enabled() bool {
	if os.Getenv("NO_COLOR") != "" || os.Getenv("CI") != "" || os.Getenv("TERM") == "dumb" {
		return false
	}
	fi, err := os.Stderr.Stat()
	return err == nil && (fi.Mode()&os.ModeCharDevice) != 0
}

func Start(label string) *Spinner {
	s := &Spinner{
		label: label, status: "starting", percent: -1,
		metrics: map[string]string{}, started: time.Now(),
		stop: make(chan struct{}), done: make(chan struct{}), tty: Enabled(),
	}
	if !s.tty {
		fmt.Fprintf(os.Stderr, "▶ %s\n", label)
		close(s.done)
		return s
	}
	go s.loop()
	return s
}

func (s *Spinner) SetStatus(status string) {
	s.mu.Lock()
	s.status = strings.TrimSpace(status)
	s.mu.Unlock()
}

func (s *Spinner) SetProgress(percent float64, status string) {
	if percent < 0 { percent = 0 }
	if percent > 100 { percent = 100 }
	s.mu.Lock()
	s.percent = percent
	if strings.TrimSpace(status) != "" { s.status = strings.TrimSpace(status) }
	s.mu.Unlock()
}

func (s *Spinner) SetMetric(key string, value any) {
	key = strings.TrimSpace(key)
	if key == "" { return }
	s.mu.Lock()
	s.metrics[key] = fmt.Sprint(value)
	s.mu.Unlock()
}

func (s *Spinner) SetMetrics(values map[string]any) {
	s.mu.Lock()
	for k, v := range values {
		if strings.TrimSpace(k) != "" { s.metrics[k] = fmt.Sprint(v) }
	}
	s.mu.Unlock()
}

func (s *Spinner) ReplaceMetrics(values map[string]any) {
	s.mu.Lock()
	s.metrics = map[string]string{}
	for k, v := range values {
		if strings.TrimSpace(k) != "" { s.metrics[k] = fmt.Sprint(v) }
	}
	s.mu.Unlock()
}

func (s *Spinner) snapshot() (string, string, float64, map[string]string, time.Duration) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	m := make(map[string]string, len(s.metrics))
	for k,v := range s.metrics { m[k]=v }
	return s.label, s.status, s.percent, m, time.Since(s.started)
}

func metricLine(metrics map[string]string, limit int) string {
	if len(metrics)==0 { return "" }
	keys:=make([]string,0,len(metrics))
	for k:=range metrics { keys=append(keys,k) }
	sort.Strings(keys)
	parts:=make([]string,0,len(keys))
	for _,k:=range keys {
		parts=append(parts, fmt.Sprintf("%s=%s",k,metrics[k]))
		if limit>0 && len(parts)>=limit { break }
	}
	return strings.Join(parts,"  ")
}

func bar(percent float64, frame int) string {
	if percent < 0 {
		frames := []string{"▰▱▱▱▱▱▱▱▱▱", "▱▰▱▱▱▱▱▱▱▱", "▱▱▰▱▱▱▱▱▱▱", "▱▱▱▰▱▱▱▱▱▱", "▱▱▱▱▰▱▱▱▱▱", "▱▱▱▱▱▰▱▱▱▱", "▱▱▱▱▱▱▰▱▱▱", "▱▱▱▱▱▱▱▰▱▱", "▱▱▱▱▱▱▱▱▰▱", "▱▱▱▱▱▱▱▱▱▰"}
		return frames[frame%len(frames)]
	}
	filled:=int(percent/10.0+0.5)
	if filled<0 { filled=0 }; if filled>10 { filled=10 }
	return strings.Repeat("▰",filled)+strings.Repeat("▱",10-filled)
}

func (s *Spinner) loop() {
	defer close(s.done)
	colors := []string{"\x1b[38;5;45m","\x1b[38;5;51m","\x1b[38;5;87m","\x1b[38;5;123m","\x1b[38;5;159m","\x1b[38;5;201m"}
	t:=time.NewTicker(120*time.Millisecond); defer t.Stop()
	i:=0
	for {
		select {
		case <-s.stop:
			fmt.Fprint(os.Stderr,"\r\x1b[2K")
			return
		case <-t.C:
			label,status,pct,metrics,elapsed:=s.snapshot()
			pctText:=" --.-%"
			if pct>=0 { pctText=fmt.Sprintf("%6.1f%%",pct) }
			fmt.Fprintf(os.Stderr,"\r\x1b[2K%s%s\x1b[0m %s %s  %-22s  %s",
				colors[i%len(colors)],bar(pct,i),pctText,label,status,elapsed.Round(time.Second))
			if ml:=metricLine(metrics,4); ml!="" { fmt.Fprintf(os.Stderr,"  \x1b[38;5;244m%s\x1b[0m",ml) }
			i++
		}
	}
}

func (s *Spinner) Summary(title string) {
	if !s.tty { return }
	_,_,_,metrics,elapsed:=s.snapshot()
	if strings.TrimSpace(title)=="" { title=s.label+" metrics" }
	fmt.Fprintf(os.Stderr,"\x1b[38;5;45m┌─ %s \x1b[0m\n",title)
	keys:=make([]string,0,len(metrics))
	for k:=range metrics { keys=append(keys,k) }
	sort.Strings(keys)
	for _,k:=range keys {
		fmt.Fprintf(os.Stderr,"\x1b[38;5;244m│\x1b[0m %-22s \x1b[38;5;87m%s\x1b[0m\n",k,metrics[k])
	}
	fmt.Fprintf(os.Stderr,"\x1b[38;5;244m│\x1b[0m %-22s \x1b[38;5;87m%s\x1b[0m\n","elapsed",elapsed.Round(time.Millisecond))
	fmt.Fprintln(os.Stderr,"\x1b[38;5;45m└────────────────────────────────────────\x1b[0m")
}

func (s *Spinner) Stop(ok bool) {
	s.once.Do(func() {
		if s.tty {
			close(s.stop)
			<-s.done
		}
		icon,color:="✓","\x1b[38;5;82m"
		if !ok { icon,color="✗","\x1b[38;5;196m" }
		if s.tty {
			_,status,pct,_,elapsed:=s.snapshot()
			pctText:=""
			if pct>=0 { pctText=fmt.Sprintf(" %.1f%%",pct) }
			fmt.Fprintf(os.Stderr,"%s%s\x1b[0m %s%s  %s  %s\n",color,icon,s.label,pctText,status,elapsed.Round(time.Millisecond))
		}
	})
}

func Label(args ...string) string { return strings.TrimSpace(strings.Join(args," ")) }
