import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'AICB Documentation',
  tagline: 'Autonomous Open-Source AI Conversational Commerce & Multi-Agent Studio',
  favicon: 'img/favicon.ico',


  url: 'https://agentos.aicb.sannex.ng',
  baseUrl: '/',

  organizationName: 'sannex-tech',
  projectName: 'aicb',

  onBrokenLinks: 'warn',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

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
          blogTitle: 'AICB Platform Releases & Changelogs',
          blogDescription: 'Official version updates, new features, and security patches for AICB instances.',
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
      title: 'AICB Docs',
      logo: {
        alt: 'AICB Logo',
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
          href: 'https://github.com/sannex-tech/aicb',
          label: 'GitHub',
          position: 'right',
        },
        {
          href: 'https://github.com/sponsors/sannex',
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
          title: 'AICB Ecosystem',
          items: [
            {
              label: 'AICB GitHub Repository',
              href: 'https://github.com/sannex-tech/aicb',
            },
            {
              label: 'Sannex Agent SDK (PyPI)',
              href: 'https://pypi.org/project/sannex-agent/',
            },
            {
              label: 'Sannex Agent SDK (npm)',
              href: 'https://www.npmjs.com/package/@sannex/agent',
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
              label: 'Sponsor AICB on GitHub',
              href: 'https://github.com/sponsors/sannex',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Sannex Tech LTD. AICB is free and open source under the MIT License.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'typescript'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
