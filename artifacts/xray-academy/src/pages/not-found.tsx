import { ShieldAlert } from 'lucide-react';
import { Link } from 'wouter';
import { Button } from '@/components/ui/button';

export default function NotFound() {
  return (
    <div className="flex h-full w-full items-center justify-center bg-background p-4 relative overflow-hidden flex-col">
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#1B263B_1px,transparent_1px),linear-gradient(to_bottom,#1B263B_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_50%,#000_70%,transparent_100%)] opacity-20 pointer-events-none"></div>
      
      <div className="z-10 flex flex-col items-center max-w-md text-center">
        <ShieldAlert className="h-20 w-20 text-destructive mb-6" />
        <h1 className="text-4xl font-bold tracking-tight mb-2 text-foreground">404 - Restricted Area</h1>
        <p className="text-muted-foreground mb-8">The terminal node you are trying to access does not exist or requires higher clearance.</p>
        <Button asChild>
          <Link href="/">Return to Main Console</Link>
        </Button>
      </div>
    </div>
  );
}