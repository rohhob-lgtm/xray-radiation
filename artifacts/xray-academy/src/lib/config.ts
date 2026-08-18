// Public-facing lockdown for the Translation Studio.
//
// Locked (PUBLIC_MODE true): the UI hides all admin/technical controls so a
// general user can only upload a document, pick a language, translate, download.
//
// An admin unlocks the full panel at /admin with ADMIN_KEY. The client stores a
// local 'ts_admin' flag (to reveal controls) and the backend flags the session
// is_admin (the real authority it checks). PUBLIC_MODE is evaluated once per page
// load, so unlocking / previewing reloads the app.
//
// "Preview as public" lets an unlocked admin view the locked UI temporarily
// (ts_preview_public flag) without logging out — a floating banner brings them
// back to the admin view.

export function isAdminUnlocked(): boolean {
  try {
    return localStorage.getItem('ts_admin') === '1';
  } catch {
    return false;
  }
}

export function isPreviewingPublic(): boolean {
  try {
    return localStorage.getItem('ts_preview_public') === '1';
  } catch {
    return false;
  }
}

// An unlocked admin who is deliberately viewing the public (locked) UI.
export const ADMIN_PREVIEWING_PUBLIC = isAdminUnlocked() && isPreviewingPublic();

// Locked/public view for anyone who isn't an unlocked admin — OR an admin who
// toggled "Preview as public".
export const PUBLIC_MODE = !isAdminUnlocked() || isPreviewingPublic();
