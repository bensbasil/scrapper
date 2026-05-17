import { NextResponse } from 'next/server';
import { query } from '@/lib/db';

export async function DELETE() {
  try {
    // We delete from businesses, and CASCADE should handle the rest 
    // if the schema was set up with ON DELETE CASCADE.
    // To be absolutely safe for this MVP, we'll clear the main tables.
    
    await query('DELETE FROM business_reports');
    await query('DELETE FROM scoring_results');
    await query('DELETE FROM website_analyses');
    await query('DELETE FROM outreach_drafts');
    await query('DELETE FROM businesses');
    
    return NextResponse.json({ success: true, message: 'Database cleared successfully.' });
  } catch (error: any) {
    console.error('Delete Error:', error);
    return NextResponse.json({ success: false, error: error.message }, { status: 500 });
  }
}
