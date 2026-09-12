import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'CommB Documentation',
  tagline: 'Autonomous Open-Source AI Conversational Commerce & Multi-Agent Studio',
  favicon: 'img/favicon.ico',


  url: 'https://agentos.commb.sannex.ng',
  baseUrl: '/',

  organizationName: 'sannex-01',
  projectName: 'commb',

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  markdown: {
    mermaid: true,
  },
  themes: ['@docusaurus/theme-mermaid'],

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: 'docs',
        },
        blog: {
          routeBasePath: 'releases',
          blogTitle: 'CommB Platform Releases & Changelogs',
          blogDescription: 'Official version updates, new features, and security patches for CommB instances.',
          showReadingTime: false,
          postsPerPage: 'ALL',
        },
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'dark',
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'CommB Docs',
      logo: {
        alt: 'CommB Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'tutorialSidebar',
          position: 'left',
          label: 'Documentation',
        },
        {to: '/releases', label: 'Releases & Changelog', position: 'left'},
        {
          href: 'https://github.com/sannex-01/commb',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://github.com/sponsors/sannex-01',
          label: '❤️ Sponsor',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            {
              label: 'Overview & Architecture',
              to: '/docs/intro',
            },
            {
              label: 'Quickstart with Docker',
              to: '/docs/getting-started/quickstart',
            },
            {
              label: 'Multi-Agent Studio',
              to: '/docs/features/agents-studio',
            },
            {
              label: 'Messaging Channels',
              to: '/docs/features/channels',
            },
          ],
        },
        {
          title: 'CommB Ecosystem',
          items: [
            {
              label: 'CommB GitHub Repository',
              href: 'https://github.com/sannex-01/commb',
            },
            {
              label: 'Sannex Agent SDK (PyPI)',
              href: 'https://pypi.org/project/commb-agent/',
            },
            {
              label: 'Sannex Agent SDK (npm)',
              href: 'https://www.npmjs.com/package/@commb/agent',
            },
          ],
        },
        {
          title: 'Community & Support',
          items: [
            {
              label: 'Platform Releases',
              to: '/releases',
            },
            {
              label: 'Sponsor CommB on GitHub',
              href: 'https://github.com/sponsors/sannex-01',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Sannex Tech LTD. CommB is free and open source under the MIT License.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'typescript'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
