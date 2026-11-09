declare namespace App {
  interface Locals {
    /** The path a page asked for before it rewrote to `/404`, which `404.astro` names. */
    notFoundPath?: string;
  }
}
