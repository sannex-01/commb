import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  icon: string;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Multi-Agent Studio & Custom Personas',
    icon: '🤖',
    description: (
      <>
        Deploy specialized assistant personas (Sales, VIP Support, Billing) with custom system prompts,
        LLM provider selection (Gemini, OpenAI, Claude, Groq), and fine-grained Access Groups.
      </>
    ),
  },
  {
    title: 'Omnichannel Commerce & Paystack',
    icon: '💳',
    description: (
      <>
        Turn customer conversations into instant checkouts across WhatsApp Cloud API, Telegram Bot,
        and embeddable Website Widget with automated Paystack payment verification.
      </>
    ),
  },
  {
    title: '100% Self-Hosted & Private',
    icon: '🔒',
    description: (
      <>
        Zero lock-in. Run on Docker, Coolify, or any VPS. Your customer data, chat transcripts,
        and RAG knowledge base stay 100% private to your self-hosted instance.
      </>
    ),
  },
];

function Feature({title, icon, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center margin-bottom--md">
        <span style={{fontSize: '3.5rem'}} role="img">{icon}</span>
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p className="text--muted">{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features} style={{padding: '4rem 0'}}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
