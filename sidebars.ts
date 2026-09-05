import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  tutorialSidebar: [
    {
      type: 'doc',
      id: 'intro',
      label: 'Overview & Architecture',
    },
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      items: [
        'getting-started/quickstart',
        'getting-started/cli-reference',
        'getting-started/coolify',
      ],
    },
    {
      type: 'category',
      label: 'Platform Features',
      collapsed: false,
      items: [
        'features/agents-studio',
        'features/access-groups',
        'features/channels',
        'features/commerce',
        'features/rag',
      ],
    },
    {
      type: 'category',
      label: 'Developer SDKs',
      collapsed: false,
      items: [
        'sdk/overview',
        'sdk/telemetry-and-sync',
      ],
    },
  ],
};

export default sidebars;
