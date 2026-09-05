import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'Sannex AgentOS & AICB Docs',
  tagline: 'Autonomous Conversational Commerce, Multi-Agent Studio & Telemetry Infrastructure',
  favicon: 'img/favicon.ico',

  future: {
    v4: true,
  },

  url: 'https://agentos.aicb.sannex.ng',
  baseUrl: '/',

  organizationName: 'sannex-tech',
  projectName: 'aicb-docs',

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
          blogTitle: 'AICB Platform Releases & Changelog',
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
      title: 'AgentOS',
      logo: {
        alt: 'AgentOS Logo',
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
              label: 'Quickstart (Docker)',
              to: '/docs/getting-started/quickstart',
            },
            {
              label: 'Multi-Agent Studio',
              to: '/docs/features/agents-studio',
            },
            {
              label: 'Python & JS SDKs',
              to: '/docs/sdk/overview',
            },
          ],
        },
        {
          title: 'Ecosystem',
          items: [
            {
              label: 'AgentOS Portal',
              href: 'https://agentos.aicb.sannex.ng',
            },
            {
              label: 'AICB GitHub',
              href: 'https://github.com/sannex-tech/aicb',
            },
            {
              label: 'Sannex Agent SDK',
              href: 'https://github.com/sannex-tech/sannex-agent',
            },
          ],
        },
        {
          title: 'Community',
          items: [
            {
              label: 'Releases',
              to: '/releases',
            },
            {
              label: 'Sponsor on GitHub',
              href: 'https://github.com/sponsors/sannex',
            },
          ],
        },
      ],
      copyright: `Copyright © ${new Date().getFullYear()} Sannex Tech LTD. Open source under MIT License.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'json', 'python', 'typescript'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
