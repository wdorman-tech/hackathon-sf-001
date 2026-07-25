import "@fontsource-variable/dm-sans"
import { EdgeLines } from "@/components/EdgeLines"
import { Nav } from "@/components/sections/Nav"
import { Hero } from "@/components/sections/Hero"
import { HowItWorks } from "@/components/sections/HowItWorks"
import { Engine } from "@/components/sections/Engine"
import { Proof } from "@/components/sections/Proof"
import { Trust } from "@/components/sections/Trust"
import { CTA } from "@/components/sections/CTA"
import { Footer } from "@/components/sections/Footer"

function App() {
  return (
    <>
      <div className="grain-overlay" aria-hidden="true" />
      <EdgeLines />
      <Nav />
      <main>
        <Hero />
        <HowItWorks />
        <Engine />
        <Proof />
        <Trust />
        <CTA />
      </main>
      <Footer />
    </>
  )
}

export default App
