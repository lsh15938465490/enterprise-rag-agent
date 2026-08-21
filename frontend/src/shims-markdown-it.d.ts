declare module "markdown-it" {
  export default class MarkdownIt {
    constructor(opts?: Record<string, unknown>);
    render(src: string): string;
  }
}
