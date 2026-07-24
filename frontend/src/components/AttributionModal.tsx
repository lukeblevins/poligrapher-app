import { Modal } from "./Modal";

interface AttributionSource {
  name: string;
  href: string;
  description: string;
  secondaryHref?: string;
  secondaryLabel?: string;
}

const SOURCES: AttributionSource[] = [
  {
    name: "PoliGraph — original research and repository",
    href: "https://github.com/UCI-Networking-Group/PoliGraph",
    description: "Created by Hao Cui, Rahmadi Trimananda, Athina Markopoulou, and Scott Jordan at UC Irvine; published at USENIX Security 2023.",
    secondaryHref: "https://www.usenix.org/conference/usenixsecurity23/presentation/cui",
    secondaryLabel: "Read and cite the paper",
  },
  {
    name: "Enhanced PoliGraph fork",
    href: "https://github.com/lukeblevins/PoliGraph",
    description: "The application-specific fork of the original UCI knowledge-graph pipeline executed by this project.",
  },
  {
    name: "policy-scorer",
    href: "https://github.com/lukeblevins/policy-scorer",
    description: "Privacy, GDPR, and readability assessment tooling used after graph generation.",
  },
  {
    name: "Open Terms Archive",
    href: "https://opentermsarchive.org/",
    description: "Open service declarations used to locate maintained privacy-policy sources and extraction metadata.",
  },
  {
    name: "GitHub REST API",
    href: "https://docs.github.com/en/rest",
    description: "Used to read the public Open Terms Archive declarations catalog; results are cached by the backend.",
  },
  {
    name: "S&P 500 constituents — Data Packages",
    href: "https://github.com/datasets/s-and-p-500-companies",
    description: "Refreshable open constituent snapshot used to maintain the S&P 500 company collection, including ticker, SEC CIK, and GICS sector metadata.",
    secondaryHref: "https://www.spglobal.com/spdji/en/indices/equity/sp-500/",
    secondaryLabel: "S&P Dow Jones Indices overview",
  },
  {
    name: "Wikidata",
    href: "https://www.wikidata.org/",
    description: "Official company website metadata matched through SEC Central Index Keys, used as a discovery anchor when an index constituent has no saved policy source.",
  },
  {
    name: "Internet Archive Wayback Machine",
    href: "https://archive.org/web/",
    description: "Fallback source for historical copies when a live privacy-policy page cannot be retrieved.",
  },
];

export function AttributionModal({ onClose }: { onClose: () => void }) {
  return (
    <Modal title="Data sources & attribution" onClose={onClose} wide>
      <p className="max-w-xl text-sm leading-6 text-slate-600 dark:text-slate-400">
        This research application orchestrates independent open-source tools and public web services.
        Their names identify dependencies and data provenance; they are not the name of this research project.
      </p>
      <div className="mt-5 divide-y divide-slate-200 rounded-md border border-slate-300 dark:divide-slate-800 dark:border-slate-700">
        {SOURCES.map((source) => (
          <div key={source.name} className="p-4">
            <a
              href={source.href}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-semibold text-teal-800 hover:underline dark:text-teal-300"
            >
              {source.name}
            </a>
            <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{source.description}</p>
            {source.secondaryHref && (
              <a href={source.secondaryHref} target="_blank" rel="noreferrer" className="mt-1.5 inline-block text-xs font-semibold text-teal-700 hover:underline dark:text-teal-400">
                {source.secondaryLabel}
              </a>
            )}
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs leading-5 text-slate-500 dark:text-slate-400">
        Source availability and licensing remain governed by each upstream project or collection.
        When publishing results produced with PoliGraph, cite the original authors and USENIX Security 2023 paper.
        Company marks are requested from each company’s public website favicon and fall back to initials when unavailable.
      </p>
    </Modal>
  );
}
