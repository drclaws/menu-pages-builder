"""Static checks of the page script and its motion styles (no JavaScript engine required)."""

import gzip
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "assets" / "app.js"
APP_CSS = ROOT / "assets" / "app.css"

#: Every module of the script, in the order they are registered.
MODULES = ["tabs", "reveal", "sectionNav"]


def module_code(code, name):
    """A module's code (comments dropped): from the first declaration after
    its header comment up to the next module's header."""
    starts = {"tabs": "var TABS_STEPS", "reveal": "var REVEAL_INSET", "sectionNav": "var NAV_SLACK"}
    start = code.index(starts[name])
    following = [code.index(mark) for mark in starts.values() if code.index(mark) > start]
    return code[start:min(following)] if following else code[start:code.rindex("}());")]


def strip_comments(source):
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(^|[^:'\"])//[^\n]*", r"\1", source)


def css_section(css, number, name):
    """A numbered section of the style sheet, comments dropped."""
    start = css.index("\n   %s. %s\n" % (number, name))
    following = re.search(r"\n   \d+a?\. ", css[start + 1:])
    end = start + 1 + following.start() if following else len(css)
    return strip_comments("/*" + css[start:end] + "*/")


def css_ms(css, token):
    value = re.search(r"\n\s*" + re.escape(token) + r":\s*([\d.]+)(ms|s)\b", css)
    number = float(value.group(1))
    return number * 1000 if value.group(2) == "s" else number


class AppJsSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = APP_JS.read_text(encoding="utf-8")
        cls.code = strip_comments(cls.raw)

    def test_first_action_adds_js_class(self):
        statements = [line.strip() for line in self.code.splitlines() if line.strip()]
        self.assertEqual(statements[0], "(function () {")
        self.assertEqual(statements[1], "'use strict';")
        self.assertEqual(statements[2], "document.documentElement.classList.add('js');")

    def test_single_iife_without_globals(self):
        self.assertTrue(self.code.strip().endswith("}());"))
        self.assertEqual(self.code.count("}());"), 1)
        self.assertTrue(self.code.lstrip().startswith("(function () {"))
        self.assertNotRegex(self.code, r"\bwindow\.\w+\s*=[^=]")
        self.assertNotRegex(self.code, r"\bglobalThis\b")

    def test_no_constructs_forbidden_by_csp(self):
        for pattern in (r"\beval\s*\(", r"\bnew\s+Function\b", r"\bFunction\s*\(",
                        r"\binnerHTML\b", r"\bouterHTML\b", r"\binsertAdjacentHTML\b",
                        r"\bdocument\.write", r"\bimport\s*\(",
                        r"set(?:Timeout|Interval)\s*\(\s*['\"`]",
                        r"setAttribute\(\s*['\"]style['\"]", r"\.style\.cssText", r"\.style\s*=[^=]",
                        r"\.style\.[a-zA-Z]+\s*=[^=]"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)
        # styles change through CSSOM custom properties only
        methods = set(re.findall(r"\.style\.(\w+)\(", self.code))
        self.assertEqual(methods, {"setProperty", "removeProperty"})

    def test_no_external_urls_or_network_calls(self):
        # "\b" never matches before "//" (a quote is not a word character), so
        # a protocol-relative address is looked for after a quote or a bracket
        for pattern in (r"(?i)https?://", r"""(?i)['"(]//[a-z0-9.-]+\.[a-z]{2,}"""):
            self.assertNotRegex(self.raw, pattern)
        for pattern in (r"\bfetch\s*\(", r"\bXMLHttpRequest\b", r"\bsendBeacon\b",
                        r"\bWebSocket\b", r"\bEventSource\b", r"\blocalStorage\b",
                        r"\bsessionStorage\b", r"\bdocument\.cookie\b", r"\bindexedDB\b"):
            self.assertNotRegex(self.code, pattern)

    def test_modules_go_through_the_registry(self):
        self.assertEqual(re.findall(r"\bregister\('([a-zA-Z-]+)',", self.code), MODULES)
        # every init runs inside try/catch and failures are reported as warnings
        runner = self.code[self.code.index("function start()"):]
        runner = runner[:runner.index("document.addEventListener")]
        self.assertRegex(runner, r"try\s*\{\s*module\.init\(document\);\s*\}"
                                 r"\s*catch\s*\(error\)\s*\{\s*report\(module\.name, error\);")
        reporter = self.code[self.code.index("function report("):self.code.index("function start()")]
        self.assertIn("console.warn", reporter)
        # only the module name and the error type, never page data
        self.assertIn("error && error.name ? error.name : 'Error'", reporter)
        self.assertEqual(self.code.count("console.warn"), 1, "failures are reported in one place")
        self.assertNotRegex(self.code, r"console\.(?:log|error|info|debug)\b")

    def test_selectors_use_data_attributes_only(self):
        selectors = re.findall(r"(?:querySelector(?:All)?|closest)\(\s*([^)]*)\)", self.code)
        self.assertTrue(selectors)
        for selector in selectors:
            with self.subTest(selector=selector):
                self.assertRegex(selector, r"^'\[data-[a-z-]+\]'$")
        self.assertNotRegex(self.code, r"getElementsByClassName|getElementsByTagName")
        # an element by its id only where the id comes from the markup: the
        # fragment of a navigation bar link
        self.assertEqual(self.code.count("getElementById("), 1)
        self.assertIn("doc.getElementById(href.slice(1))", module_code(self.code, "sectionNav"))

    def test_es2017_compatible_syntax(self):
        for pattern in (r"\?\.", r"\?\?", r"\bawait\b.*\bfor\b", r"#\w+\s*[=(;]",
                        r"\bstatic\s*\{", r"\.replaceAll\(", r"\.at\(", r"=>", r"\blet\b",
                        r"\bconst\b", r"\bclass\b", r"`"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.code, pattern)

    def test_size_stays_small(self):
        # Our own code, not a library: without comments the file is about
        # 15 KB (the reveal over a third of it, the navigation bar and the
        # tabs about a quarter each); about 6.3 KB gzipped with comments.
        # Raise the limits deliberately, when a module needs it, not to make
        # room in advance.
        self.assertLess(len(self.code.encode("utf-8")), 16 * 1024)
        self.assertLess(len(gzip.compress(self.raw.encode("utf-8"), 9)), 8 * 1024)

    def test_the_script_has_no_text_of_its_own(self):
        # every text of the page lives in the markup
        self.assertTrue(self.raw.isascii())
        self.assertNotRegex(self.code, r"\.(?:textContent|innerText|nodeValue|data)\s*=[^=]|"
                                       r"createElement|createTextNode|appendChild|\.append\(|"
                                       r"\.prepend\(|\.before\(|\.after\(")
        self.assertNotRegex(self.code, r"setAttribute\('(?:aria-label|aria-description|title|alt|placeholder)'")
        # the attributes the script writes carry states and links, never words
        written = set(re.findall(r"setAttribute\('([\w-]+)'", self.code))
        self.assertEqual(written, {"aria-selected", "role", "tabindex", "aria-labelledby", "aria-current"})

    def test_viewport_changes_reach_the_reveal_without_the_observer(self):
        for event in ("resize", "orientationchange"):
            self.assertIn("window.addEventListener('%s', onViewportChange);" % event, self.code)
            self.assertIn("window.removeEventListener('%s', onViewportChange);" % event, self.code)
        # an inner scroller does not bubble its scroll to window: caught in
        # the capture phase, removed with the same flag
        self.assertIn("window.addEventListener('scroll', onViewportChange, { passive: true, capture: true });",
                      self.code)
        self.assertIn("window.removeEventListener('scroll', onViewportChange, true);", self.code)
        self.assertIn("requestAnimationFrame(onFrame)", self.code)


class TabsSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = strip_comments(APP_JS.read_text(encoding="utf-8"))
        cls.code = code
        start = code.index("var TABS_STEPS")
        end = code.index("\n  });", code.index("register('tabs'")) + len("\n  });")
        cls.module = code[start:end]
        cls.css = APP_CSS.read_text(encoding="utf-8")
        components = css_section(cls.css, "5", "Components")
        cls.tabs_css = components[components.index(".sets__panel {"):]

    def function(self, name):
        """Source of a module function, up to the next declaration at its level."""
        if name == "startTabs":
            return self.module[self.module.index("function startTabs("):
                               self.module.index("register('tabs'")].rstrip()
        at = self.module.index("function %s(" % name)
        indent = at - self.module.rindex("\n", 0, at) - 1
        body = self.module[at:]
        following = re.search(r"\n {%d}(?:function \w+\(|var \w+ = |register\(|try \{)" % indent, body)
        return body[:following.start() + 1] if following else body

    def test_one_instance_per_widget_each_in_its_own_try(self):
        init = self.module[self.module.index("register('tabs'"):]
        self.assertRegex(init, r"querySelectorAll\('\[data-tabs\]'\), function \(widget\) \{\s*"
                               r"try \{\s*startTabs\(widget\);\s*\}\s*catch \(error\) \{\s*"
                               r"report\('tabs', error\);")
        # every query an instance makes starts from its own root
        start = self.function("startTabs")
        for query in re.findall(r"(\w+)\.querySelector(?:All)?\(", start):
            self.assertIn(query, ("widget", "tablist"))
        self.assertNotRegex(self.module, r"\bdocument\.querySelector")

    def test_runs_before_reveal_measures_the_page(self):
        # hiding the panels shortens the page; reveal must measure the final layout
        self.assertLess(self.code.index("register('tabs'"), self.code.index("register('reveal'"))

    def test_fewer_than_two_tabs_or_unmatched_panels_change_nothing(self):
        start = self.function("startTabs")
        # every panel belongs to exactly one tab: as many as the panels, each
        # found, none left out (two tabs naming one panel leave another out)
        guard = ("if (tabs.length < 2 || panels.length !== all.length || "
                 "panels.indexOf(undefined) !== -1 ||\n"
                 "        all.some(function (panel) { return panels.indexOf(panel) === -1; })) {\n"
                 "      return;\n    }")
        self.assertIn(guard, start)
        # the guard comes before anything is changed
        self.assertLess(start.index(guard), start.index("setAttribute"))
        self.assertLess(start.index(guard), start.index(".hidden"))

    def test_the_first_tab_is_selected_and_time_plays_no_part(self):
        start = self.function("startTabs")
        body = start[start.rindex("try {"):]
        self.assertEqual(re.findall(r"\bselect\(([^)]*)\);", body), ["0, false"])
        for pattern in (r"\bDate\b", r"setTimeout|setInterval|clearTimeout", r"visibilitychange",
                        r"pageshow", r"focusout", r"data-events", r"modalOpen", r"is-past|is-now"):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.module, pattern)

    def test_handlers_are_guarded(self):
        listeners = re.findall(r"\.addEventListener\('[a-z]+', (\w+)\);", self.module)
        self.assertEqual(sorted(listeners), ["onClick", "onKeyDown"])
        for listener in listeners:
            with self.subTest(listener=listener):
                self.assertRegex(self.module, r"var %s = guarded\(function" % listener)
        guarded = self.function("guarded")
        self.assertRegex(guarded, r"catch \(error\) \{\s*restore\(\);\s*report\('tabs', error\);")
        # a failure while starting also goes back to the markup as it was
        start = self.function("startTabs")
        self.assertRegex(start, r"\} catch \(error\) \{\s*restore\(\);\s*throw error;\s*\}\s*\}$")

    def test_restore_returns_the_view_without_the_script(self):
        restore = self.function("restore")
        for step in ("tablist.hidden = true;", "tablist.style.removeProperty('--tabs-count');",
                     "panel.hidden = false;", "panel.removeAttribute('role');",
                     "panel.removeAttribute('tabindex');",
                     "panel.setAttribute('aria-labelledby', labelledBy[i]);",
                     "panel.removeAttribute('aria-labelledby');"):
            with self.subTest(step=step):
                self.assertIn(step, restore)
        for listener in re.findall(r"\.addEventListener\(('[a-z]+', \w+)\);", self.module):
            with self.subTest(listener=listener):
                self.assertIn(".removeEventListener(%s);" % listener, restore)

    def test_the_tab_list_is_shown_last_and_counted_through_cssom(self):
        start = self.function("startTabs")
        body = start[start.rindex("try {"):]
        self.assertTrue(body[:body.index("} catch")].rstrip().endswith("tablist.hidden = false;"))
        self.assertIn("tablist.style.setProperty('--tabs-count', String(tabs.length));", start)
        self.assertNotRegex(self.module, r"setAttribute\('style'|\.style\.cssText|\.style\s*=")

    def test_tabs_follow_the_aria_pattern(self):
        start = self.function("startTabs")
        for step in ("panel.setAttribute('role', 'tabpanel');", "panel.setAttribute('tabindex', '0');",
                     "panel.setAttribute('aria-labelledby', tabs[i].id);"):
            self.assertIn(step, start)
        select = self.function("select")
        for step in ("tab.setAttribute('aria-selected', on ? 'true' : 'false');",
                     "tab.tabIndex = on ? 0 : -1;", "panels[i].hidden = !on;"):
            self.assertIn(step, select)
        # both axes, because the tabs stand in a row or in a column
        for key in ("ArrowLeft", "ArrowUp", "ArrowRight", "ArrowDown"):
            self.assertIn(key + ":", self.module)
        keys = self.module[self.module.index("var onKeyDown"):]
        self.assertIn("event.altKey || event.ctrlKey || event.metaKey || event.shiftKey", keys)
        self.assertIn("event.preventDefault();", keys)
        self.assertIn("select(to, true);", keys)
        self.assertIn("'Home'", keys)
        self.assertIn("'End'", keys)
        self.assertIn("% tabs.length", keys)
        # ids are read from the markup, never put together
        self.assertIn("tab.getAttribute('aria-controls')", start)
        self.assertNotRegex(self.module, r"'--(?:tab|panel|title)'|\+\s*'-")

    def test_tab_styles(self):
        tab = re.search(r"\.sets__tab \{([^}]*)\}", self.tabs_css).group(1)
        self.assertIn("min-block-size: var(--tap-min);", tab)
        self.assertIn("var(--duration-fast)", tab)
        self.assertIn("var(--tabs-count", self.tabs_css)
        self.assertIn("var(--sets-tab-min)", self.tabs_css)
        self.assertNotRegex(self.tabs_css, r"@container|@media[^{]*width|:has\(|animation|data-reveal|@keyframes")
        for state in ('[aria-selected="true"]', ":focus-visible", ":active"):
            self.assertIn(".sets__tab" + state, self.tabs_css)
        outside = re.sub(r"@media \(hover: hover\)\s*\{(?:[^{}]*\{[^{}]*\})*\s*\}", "", self.tabs_css)
        self.assertNotIn(":hover", outside)
        self.assertIn(".sets__tab:hover", self.tabs_css)


class MotionStylesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.section = css_section(APP_CSS.read_text(encoding="utf-8"), "7", "Motion & reveal")

    def test_hidden_states_require_js_class_and_marker(self):
        rules = re.findall(r"([^{}]+)\{[^{}]*\bopacity:\s*0\b[^{}]*\}", self.section)
        self.assertTrue(rules)
        for selector in rules:
            for part in selector.split(","):
                self.assertRegex(part.strip(), r"^html\.js\.reveal-on ")

    def test_print_and_reduced_motion_show_everything(self):
        for condition in (r"print", r"\(prefers-reduced-motion: reduce\)"):
            with self.subTest(condition=condition):
                block = re.search(r"@media %s\s*\{((?:[^{}]*\{[^{}]*\})*)\s*\}" % condition, self.section)
                self.assertIsNotNone(block)
                self.assertRegex(block.group(1),
                                 r"html\.js\.reveal-on \[data-reveal\],\s*"
                                 r"html\.js\.reveal-on \[data-reveal\]:not\(\.is-revealed\) \{\s*"
                                 r"opacity: 1;\s*transform: none;\s*transition: none;\s*\}")

    def test_reveal_transition_runs_only_while_appearing(self):
        # hiding (marker set) is instant; the transition starts with is-revealed
        # and is dropped with is-settled
        self.assertIn("html.js.reveal-on [data-reveal].is-revealed:not(.is-settled) {", self.section)
        self.assertNotRegex(self.section, r"html\.js\.reveal-on \[data-reveal\]\s*\{\s*transition")
        self.assertNotRegex(self.section, r"\[data-reveal\]:not\(\.is-settled\)\s*\{")
        hidden = re.search(r"html\.js\.reveal-on \[data-reveal\]:not\(\.is-revealed\) \{([^}]*)\}",
                           self.section)
        self.assertIsNotNone(hidden)
        self.assertNotIn("transition", hidden.group(1))

    def test_reveal_uses_the_entrance_duration(self):
        rule = re.search(r"\.is-revealed:not\(\.is-settled\) \{([^}]*)\}", self.section).group(1)
        # opacity starts gently (a steep start reads as a flash), the offset decelerates
        self.assertIn("opacity var(--duration-slow) var(--ease-in-out),", rule)
        self.assertIn("transform var(--duration-slow) var(--ease-out);", rule)
        self.assertIn("transition-delay: calc(var(--reveal-index, 0) * var(--reveal-stagger));", rule)
        self.assertNotRegex(rule, r"--duration-(?:fast|base)")

    def test_only_opacity_and_vertical_transform_change(self):
        self.assertNotIn("@keyframes", self.section)
        self.assertNotIn("animation", self.section)
        transitions = re.findall(r"\btransition:\s*([^;]+);", self.section)
        self.assertTrue(transitions)
        for value in transitions:
            if value.strip() != "none":
                for part in value.split(","):
                    self.assertIn(part.split()[0], ("opacity", "transform"))
        for value in re.findall(r"\btransform:\s*([^;]+);", self.section):
            self.assertRegex(value, r"^(?:none|translateY\(var\(--reveal-distance\)\))$")
        self.assertNotRegex(self.section, r"(?<![\w-])(?:margin|inset|width|height|top|bottom|display)[\w-]*\s*:")


class RevealInvariantsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        code = strip_comments(APP_JS.read_text(encoding="utf-8"))
        module = module_code(code, "reveal")
        cls.module = module[module.index("register('reveal'"):]
        cls.code = code
        cls.css = APP_CSS.read_text(encoding="utf-8")

    def test_the_marker_is_set_last_and_only_when_it_can_work(self):
        guard = self.module[:self.module.index("var observer")]
        self.assertIn("typeof window.IntersectionObserver !== 'function'", guard)
        self.assertIn("prefersReducedMotion()", guard)
        body = self.module[self.module.rindex("try {"):]
        self.assertTrue(body[:body.index("} catch")].rstrip().endswith("root.classList.add('reveal-on');"))
        self.assertRegex(body, r"\} catch \(error\) \{\s*fail\(\);\s*throw error;")

    def test_settles_only_at_the_real_end_of_the_opacity_transition(self):
        # an event from a nested element, the transform transition or an extra
        # transitionend with elapsedTime 0 (sent while scrolling) is not the end
        end = self.module[self.module.index("function isRevealEnd("):self.module.index("function settleLater(")]
        self.assertRegex(end, r"if \(event\.target !== element\) \{\s*return false;\s*\}")
        self.assertRegex(end, r"if \(event\.type === 'transitioncancel'\) \{\s*return true;\s*\}")
        self.assertIn("return event.propertyName === 'opacity' && event.elapsedTime > 0;", end)
        later = self.module[self.module.index("function settleLater("):self.module.index("function show(")]
        self.assertIn("if (event && !isRevealEnd(event, element))", later)
        for event in ("transitionend", "transitioncancel"):
            self.assertIn("element.addEventListener('%s', done);" % event, later)
            self.assertIn("element.removeEventListener('%s', done);" % event, later)
        self.assertIn("setTimeout(done, REVEAL_SETTLE_MS)", later)

    def test_reveals_from_the_first_visible_pixel(self):
        self.assertRegex(self.code, r"\bvar REVEAL_INSET = 0;")
        self.assertIn("rootMargin: REVEAL_MARGIN", self.module)

    def test_revealed_blocks_are_never_hidden_again(self):
        self.assertNotRegex(self.module, r"classList\.remove\('is-(?:revealed|settled)'\)")
        self.assertNotRegex(self.module, r"classList\.toggle\(")
        # the marker is removed only on failure (everything becomes visible)
        self.assertEqual(self.module.count("root.classList.remove('reveal-on')"), 1)
        fail = self.module[self.module.index("function fail()"):]
        self.assertTrue(fail[:fail.index("}")].strip().endswith("finish();"))

    def test_handlers_are_guarded(self):
        for handler in ("sweep", "onFocusIn", "onFrame", "onVisibilityChange", "onIntersect"):
            with self.subTest(handler=handler):
                self.assertRegex(self.module, r"var %s = guarded\(function" % handler)
        self.assertRegex(self.module[self.module.index("function guarded("):],
                         r"catch \(error\) \{\s*fail\(\);\s*report\('reveal', error\);")

    def test_safety_timer_outlasts_the_longest_reveal(self):
        settle = int(re.search(r"REVEAL_SETTLE_MS = (\d+)", self.code).group(1))
        stagger_max = int(re.search(r"REVEAL_STAGGER_MAX = (\d+)", self.code).group(1))
        longest = css_ms(self.css, "--duration-slow") + stagger_max * css_ms(self.css, "--reveal-stagger")
        self.assertGreater(settle, longest + 200)


class SectionNavSourceTest(unittest.TestCase):
    """The navigation bar module: it marks, it never hides or scrolls the page."""

    @classmethod
    def setUpClass(cls):
        cls.code = strip_comments(APP_JS.read_text(encoding="utf-8"))
        cls.module = module_code(cls.code, "sectionNav")

    def test_registered_after_the_tabs(self):
        # the tabs change the page height before the targets are measured
        self.assertLess(self.code.index("register('tabs'"), self.code.index("register('sectionNav'"))

    def test_hooks_are_its_data_attributes_alone(self):
        hooks = sorted(set(re.findall(r"'\[(data-[a-z-]+)\]'", self.module)))
        self.assertEqual(hooks, ["data-section-nav", "data-section-nav-link", "data-section-nav-list"])
        # nothing to do without the bar or without a target
        init = self.module[self.module.index("register('sectionNav'"):]
        self.assertRegex(init, r"if \(!targets\.length\) \{\s*return;\s*\}")
        self.assertLess(init.index("if (!targets.length)"), init.index("addEventListener"))

    def test_the_mark_is_aria_current(self):
        self.assertIn("link.setAttribute('aria-current', 'true');", self.module)
        self.assertIn("link.removeAttribute('aria-current');", self.module)
        self.assertEqual(set(re.findall(r"setAttribute\('([\w-]+)'", self.module)), {"aria-current"})
        self.assertNotRegex(self.module, r"\.hidden\b|classList|\.style\.")

    def test_handlers_are_guarded_and_restore_the_view_without_the_script(self):
        listeners = re.findall(r"\.addEventListener\('([a-z]+)', (\w+)", self.module)
        self.assertEqual(sorted(listeners), [("click", "onClick"), ("focusin", "onFocus"), ("load", "onChange"),
                                             ("resize", "onChange"), ("scroll", "onScroll")])
        for name in {listener for _event, listener in listeners} | {"onFrame"}:
            with self.subTest(handler=name):
                self.assertRegex(self.module, r"var %s = guarded\(function" % name)
        guarded = self.module[self.module.index("function guarded("):]
        self.assertRegex(guarded, r"catch \(error\) \{\s*restore\(\);\s*report\('sectionNav', error\);")
        restore = self.module[self.module.index("function restore("):self.module.index("function guarded(")]
        self.assertIn("link.removeAttribute('aria-current');", restore)
        for event, listener in listeners:
            removed = "true" if event == "scroll" else listener
            with self.subTest(listener=event):
                self.assertRegex(restore, r"\.removeEventListener\('%s', %s(?:, %s)?\);" % (event, listener, removed))
        self.assertIn("clearTimeout(timer);", restore)
        # a failure while starting goes back to the view without the script as well
        self.assertRegex(self.module, r"\} catch \(error\) \{\s*restore\(\);\s*throw error;\s*\}\s*\}\);\s*$")

    def test_scroll_is_caught_in_the_capture_phase_once_a_frame(self):
        # the body scrolls the page on a touch screen: its scroll does not reach window otherwise
        self.assertIn("window.addEventListener('scroll', onScroll, { passive: true, capture: true });",
                      self.module)
        self.assertIn("window.removeEventListener('scroll', onScroll, true);", self.module)
        self.assertIn("requestAnimationFrame(onFrame)", self.module)
        self.assertRegex(self.module, r"var onChange = guarded\(function \(\) \{\s*if \(frame\) \{\s*return;")

    def test_the_page_is_scrolled_by_the_browser_alone(self):
        # scrollIntoView stops a smooth page scroll in Chromium; the
        # focus stays where the browser puts it; the link is followed as it is
        for pattern in (r"scrollIntoView", r"\.focus\(", r"preventDefault", r"\bscrollTo\b", r"\bscrollBy\b",
                        r"scrollTop\s*[-+]?=[^=]", r"window\.scroll\("):
            with self.subTest(pattern=pattern):
                self.assertNotRegex(self.module, pattern)
        # only the list scrolls sideways
        self.assertEqual(set(re.findall(r"(\w+)\.scrollLeft\s*[-+]?=[^=]", self.module)), {"list"})

    def test_a_click_holds_its_mark_while_its_scroll_goes_on(self):
        constants = dict(re.findall(r"var (NAV_[A-Z_]+) = (\d+);", self.module))
        self.assertEqual(set(constants), {"NAV_SLACK", "NAV_SETTLE_MS", "NAV_HOLD_MS"})
        self.assertLess(int(constants["NAV_SETTLE_MS"]), int(constants["NAV_HOLD_MS"]))
        click = self.module[self.module.index("var onClick"):]
        self.assertIn("held = true;", click)
        self.assertIn("timer = setTimeout(release, NAV_HOLD_MS);", click)
        scroll = self.module[self.module.index("var onScroll"):self.module.index("var onClick")]
        self.assertIn("timer = setTimeout(release, NAV_SETTLE_MS);", scroll)
        frame = self.module[self.module.index("var onFrame"):self.module.index("var onChange")]
        self.assertRegex(frame, r"if \(!held\) \{\s*mark\(find\(\)\);")

    def test_the_section_in_view(self):
        find = self.module[self.module.index("function find()"):self.module.index("function release()")]
        # the bar's bottom edge plus some slack; at the end of the page, the whole screen
        self.assertIn("scrolled() && atEnd() ? viewportHeight() :", find)
        self.assertIn("nav.getBoundingClientRect().bottom + NAV_SLACK", find)
        self.assertIn("target.getBoundingClientRect().top < limit", find)
        # the end and the scroll belong to the body when the body scrolls
        helpers = self.code[self.code.index("function bodyScrolls()"):self.code.index("var TABS_STEPS")]
        self.assertIn("window.getComputedStyle(document.body).overflowY !== 'visible'", helpers)
        self.assertIn("body.scrollTop + body.clientHeight >= body.scrollHeight - 2", helpers)


if __name__ == "__main__":
    unittest.main()
