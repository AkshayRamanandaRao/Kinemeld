/**
 * Let workflow tests act on controls in any workspace, as a user would after choosing it.
 * Before Playwright acts on a locator, ask the app to switch to the workspace that owns the
 * element (window.__kinemeldReveal). Elements outside the workspaces are unaffected.
 */
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const ACTIONS = ['scrollIntoViewIfNeeded', 'dispatchEvent', 'boundingBox', 'screenshot', 'click', 'dblclick', 'fill', 'press', 'pressSequentially', 'type', 'check', 'uncheck', 'setChecked', 'selectOption', 'focus', 'hover', 'clear', 'selectText', 'tap'];
let patched = false;

function patchLocator(page) {
  if (patched) return;
  patched = true;
  const prototype = Object.getPrototypeOf(page.locator('html'));
  for (const name of ACTIONS) {
    const original = prototype[name];
    if (typeof original !== 'function') continue;
    prototype[name] = async function (...args) {
      try {
        await this.evaluate((element) => window.__kinemeldReveal?.(element), undefined, { timeout: 4000 });
      } catch {
        // Missing, multiple or detached elements keep Playwright's own waiting and errors.
      }
      return original.apply(this, args);
    };
  }
}

function patchContextLike(target) {
  const newPage = target.newPage?.bind(target);
  if (newPage) target.newPage = async (...args) => { const page = await newPage(...args); patchLocator(page); return page; };
  const newContext = target.newContext?.bind(target);
  if (newContext) target.newContext = async (...args) => { const context = await newContext(...args); patchContextLike(context); return context; };
}

const launch = chromium.launch.bind(chromium);
chromium.launch = async (...args) => { const browser = await launch(...args); patchContextLike(browser); return browser; };
