/**
 * The Omniscient mark. The artwork lives in /public so it is also served as
 * the favicon and apple-touch-icon, and is styled by `.brand-logo` in
 * global.css (global rather than layout.css so the auth pages, which do not
 * mount the app shell, get the same mark). The brand name is always rendered
 * as text next to it, so the image is decorative here and marked as such.
 */
export function BrandLogo({ className }: { className?: string }) {
  return <img src="/logo.png" alt="" className={className ? `brand-logo ${className}` : 'brand-logo'} />;
}
