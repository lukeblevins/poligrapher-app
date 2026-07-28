import { useCallback, useRef, useState, type CSSProperties, type ReactNode } from "react";
import addIcon from "@material-symbols/svg-400/rounded/add.svg?url";
import companiesIcon from "@material-symbols/svg-400/rounded/domain.svg?url";
import companiesFilledIcon from "@material-symbols/svg-400/rounded/domain-fill.svg?url";
import collectionsIcon from "@material-symbols/svg-400/rounded/folder.svg?url";
import collectionsFilledIcon from "@material-symbols/svg-400/rounded/folder-fill.svg?url";
import collapseIcon from "@material-symbols/svg-400/rounded/menu_open.svg?url";
import expandIcon from "@material-symbols/svg-400/rounded/menu.svg?url";
import moreIcon from "@material-symbols/svg-400/rounded/keyboard_arrow_down.svg?url";
import settingsIcon from "@material-symbols/svg-400/rounded/settings.svg?url";
import settingsFilledIcon from "@material-symbols/svg-400/rounded/settings-fill.svg?url";
import scheduledIcon from "@material-symbols/svg-400/rounded/schedule.svg?url";
import scheduledFilledIcon from "@material-symbols/svg-400/rounded/schedule-fill.svg?url";

import { useLightDismiss } from "../hooks/useLightDismiss";
import type { TaskStatus } from "../api/types";
import { ImportCsvModal } from "./modals/ImportCsvModal";
import { StatusCenter } from "./StatusCenter";

type Workspace = "companies" | "collections" | "scheduled" | "about";

interface Props {
  workspace: Workspace;
  onWorkspaceChange: (workspace: Workspace) => void;
  onAddCompany: () => void;
  onViewRun?: (task: TaskStatus) => void;
}

function MaterialIcon({ src }: { src: string }) {
  return (
    <span
      className="m3-material-symbol"
      style={{ "--m3-symbol-url": `url("${src}")` } as CSSProperties}
      aria-hidden="true"
    />
  );
}

function RailItem({ active, label, icon, activeIcon, expanded, onClick }: { active: boolean; label: string; icon: ReactNode; activeIcon?: ReactNode; expanded: boolean; onClick: () => void }) {
  return (
    <button type="button" className={`m3-rail-item ${active ? "m3-rail-item-selected" : ""}`} data-expanded={expanded} aria-current={active ? "page" : undefined} aria-label={label} title={label} onClick={onClick}>
      <span className="m3-rail-icon">{active && activeIcon ? activeIcon : icon}</span>
      <span className="m3-rail-label">{label}</span>
    </button>
  );
}

const icons = {
  expand: <MaterialIcon src={expandIcon} />,
  collapse: <MaterialIcon src={collapseIcon} />,
  add: <MaterialIcon src={addIcon} />,
  companies: <MaterialIcon src={companiesIcon} />,
  companiesFilled: <MaterialIcon src={companiesFilledIcon} />,
  collections: <MaterialIcon src={collectionsIcon} />,
  collectionsFilled: <MaterialIcon src={collectionsFilledIcon} />,
  scheduled: <MaterialIcon src={scheduledIcon} />,
  scheduledFilled: <MaterialIcon src={scheduledFilledIcon} />,
  settings: <MaterialIcon src={settingsIcon} />,
  settingsFilled: <MaterialIcon src={settingsFilledIcon} />,
};

export function GlobalNavigationRail({ workspace, onWorkspaceChange, onAddCompany, onViewRun }: Props) {
  const [expanded, setExpanded] = useState(() => typeof window === "undefined" || window.innerWidth >= 1024);
  const [showImport, setShowImport] = useState(false);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);
  const dismissCreateMenu = useCallback(() => setShowCreateMenu(false), []);
  useLightDismiss(showCreateMenu, createMenuRef, dismissCreateMenu);
  return (
    <>
      <nav aria-label="Primary navigation" className={`global-navigation-rail ${expanded ? "global-navigation-rail-expanded" : "global-navigation-rail-collapsed"} hidden shrink-0 flex-col sm:flex`}>
        <div className="m3-rail-brand">
          <span className="m3-rail-brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" fill="none"><circle cx="7" cy="16" r="3" fill="currentColor" /><circle cx="24" cy="8" r="3" fill="currentColor" /><circle cx="24" cy="24" r="3" fill="currentColor" /><path d="m10 15 11-5M10 17l11 5" stroke="currentColor" strokeWidth="1.5" /></svg>
          </span>
          <span className={expanded ? "m3-rail-brand-label" : "sr-only"}>Privacy Policy<br />Analyzer</span>
          <button type="button" className="m3-rail-toggle" aria-label={expanded ? "Collapse navigation rail" : "Expand navigation rail"} title={expanded ? "Collapse navigation rail" : "Expand navigation rail"} onClick={() => { setShowCreateMenu(false); setExpanded((value) => !value); }}>{expanded ? icons.collapse : icons.expand}</button>
        </div>
        <div ref={createMenuRef} className="m3-rail-create-wrap relative">
          <div className="m3-rail-create-group">
            <button type="button" className="m3-rail-create" aria-label="Add company" title="Add company" onClick={onAddCompany}>{icons.add}<span className={expanded ? "" : "sr-only"}>Add company</span></button>
            <button type="button" className={`m3-rail-create-more ${showCreateMenu ? "m3-rail-create-more-expanded" : ""}`} aria-label="More ways to add companies" aria-haspopup="menu" aria-expanded={showCreateMenu} onClick={() => setShowCreateMenu((value) => !value)}><MaterialIcon src={moreIcon} /></button>
          </div>
          {showCreateMenu && <div role="menu" className="m3-menu absolute left-3 top-[3.5rem] z-30 w-56 p-1"><button role="menuitem" className="m3-menu-item w-full px-3 text-left" onClick={() => { setShowCreateMenu(false); setShowImport(true); }}>Import companies from CSV</button></div>}
        </div>
        <div className="flex flex-col gap-1 px-3">
          <RailItem active={workspace === "companies"} label="Companies" icon={icons.companies} activeIcon={icons.companiesFilled} expanded={expanded} onClick={() => onWorkspaceChange("companies")} />
          <RailItem active={workspace === "collections"} label="Collections" icon={icons.collections} activeIcon={icons.collectionsFilled} expanded={expanded} onClick={() => onWorkspaceChange("collections")} />
          <RailItem active={workspace === "scheduled"} label="Tasks" icon={icons.scheduled} activeIcon={icons.scheduledFilled} expanded={expanded} onClick={() => onWorkspaceChange("scheduled")} />
        </div>
        <div className="m3-rail-utilities">
          <StatusCenter
            onViewRun={onViewRun}
            onOpenWorkspace={() => onWorkspaceChange("scheduled")}
            variant="rail"
          />
          <RailItem active={workspace === "about"} label="Settings" icon={icons.settings} activeIcon={icons.settingsFilled} expanded={expanded} onClick={() => onWorkspaceChange("about")} />
        </div>
      </nav>

      <nav aria-label="Primary navigation" className="global-bottom-navigation sm:hidden">
        <RailItem active={workspace === "companies"} label="Companies" icon={icons.companies} activeIcon={icons.companiesFilled} expanded onClick={() => onWorkspaceChange("companies")} />
        <RailItem active={workspace === "collections"} label="Collections" icon={icons.collections} activeIcon={icons.collectionsFilled} expanded onClick={() => onWorkspaceChange("collections")} />
        <RailItem active={workspace === "scheduled"} label="Tasks" icon={icons.scheduled} activeIcon={icons.scheduledFilled} expanded onClick={() => onWorkspaceChange("scheduled")} />
        <RailItem active={workspace === "about"} label="Settings" icon={icons.settings} activeIcon={icons.settingsFilled} expanded onClick={() => onWorkspaceChange("about")} />
      </nav>
      {showImport && <ImportCsvModal onClose={() => setShowImport(false)} />}
    </>
  );
}
