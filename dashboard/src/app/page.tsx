import BusinessDashboard from "@/components/BusinessDashboard";
import { getBusinesses } from "@/lib/businesses";

export default async function Home() {
  const businesses = await getBusinesses();
  
  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-white">Prospects</h2>
          <p className="text-slate-400 mt-1">Real-time intelligence from your scraper.</p>
        </div>
      </div>

      <BusinessDashboard initialBusinesses={businesses} />
    </div>
  );
}
