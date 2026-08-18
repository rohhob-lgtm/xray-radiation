import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';
import RadiationSourcesPage from '@/pages/radiation-sources';

// Standalone site: the Radiation Sources & Accelerator Engineering learning
// section only, opening on the Courses experience. No auth gate and no platform
// sidebar — the page renders full-screen with its own internal navigation.
const queryClient = new QueryClient();

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RadiationSourcesPage initialSection="learn" />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
