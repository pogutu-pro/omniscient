/**
 * Every icon in the product comes from Lucide (lucide-react) so the icon
 * language stays a single, consistent, enterprise-grade system rather than
 * a mix of hand-rolled SVGs. This module re-exports the specific icons the
 * app uses under semantic names (so call sites read `<HousingIcon />`, not
 * `<Building2 />`) and applies one shared default size/stroke-width, so
 * every icon in the product is visually consistent unless a call site
 * explicitly overrides it.
 */
import {
  Activity,
  BarChart3,
  Building2,
  Check,
  ChevronDown,
  ChevronUp,
  Download,
  File,
  FileText,
  Flag,
  GraduationCap,
  History,
  Home,
  Image,
  Loader2,
  LogOut,
  MapPin,
  MessageSquare,
  Paperclip,
  Plus,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
  User,
  X,
  type LucideIcon,
  type LucideProps,
} from 'lucide-react';

const ICON_DEFAULTS = { size: 18, strokeWidth: 1.75 } satisfies Partial<LucideProps>;

function withDefaults(Icon: LucideIcon) {
  return function IconWithDefaults(props: LucideProps) {
    return <Icon {...ICON_DEFAULTS} {...props} />;
  };
}

export const HomeIcon = withDefaults(Home);
export const HousingIcon = withDefaults(Building2);
export const AcademicsIcon = withDefaults(GraduationCap);
export const PapersIcon = withDefaults(FileText);
export const ComplaintsIcon = withDefaults(Flag);
export const ProfileIcon = withDefaults(User);
export const ActivityIcon = withDefaults(Activity);
export const SendIcon = withDefaults(Send);
export const CheckIcon = withDefaults(Check);
export const CloseIcon = withDefaults(X);
export const SpinnerIcon = withDefaults(Loader2);
export const MapPinIcon = withDefaults(MapPin);
export const LogoutIcon = withDefaults(LogOut);
export const PlusIcon = withDefaults(Plus);
export const MessageIcon = withDefaults(MessageSquare);
export const HistoryIcon = withDefaults(History);
export const ChevronDownIcon = withDefaults(ChevronDown);
export const ChevronUpIcon = withDefaults(ChevronUp);
export const AdminIcon = withDefaults(ShieldCheck);
export const InsightsIcon = withDefaults(BarChart3);
export const TrashIcon = withDefaults(Trash2);
export const UploadIcon = withDefaults(Upload);
export const DownloadIcon = withDefaults(Download);
export const AttachIcon = withDefaults(Paperclip);
export const ImageFileIcon = withDefaults(Image);
export const GenericFileIcon = withDefaults(File);
