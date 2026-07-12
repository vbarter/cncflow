import * as React from "react"
import * as ProgressPrimitive from "@radix-ui/react-progress"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "../lib/utils"

const variants = cva("inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-zinc-900 disabled:pointer-events-none disabled:opacity-45", { variants: { variant: { default: "bg-zinc-950 text-white hover:bg-zinc-800", outline: "border border-zinc-300 bg-white hover:bg-zinc-100", ghost: "hover:bg-zinc-100" }, size: { default: "h-10 px-4 py-2", lg: "h-12 px-7 text-base", sm: "h-8 px-3" } }, defaultVariants: { variant: "default", size: "default" } })
export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> { asChild?: boolean }
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({className,variant,size,asChild=false,...props},ref) => { const C=asChild?Slot:"button"; return <C className={cn(variants({variant,size}),className)} ref={ref} {...props}/> })
Button.displayName="Button"
export function Card({className,...props}:React.HTMLAttributes<HTMLDivElement>){return <div className={cn("min-w-0 max-w-full overflow-hidden rounded-xl border border-zinc-200 bg-white",className)} {...props}/>}
export function Badge({className,...props}:React.HTMLAttributes<HTMLSpanElement>){return <span className={cn("inline-flex items-center rounded-full border border-zinc-300 px-2.5 py-0.5 text-xs font-medium",className)} {...props}/>}
export function Progress({value=0}:{value?:number}){return <ProgressPrimitive.Root className="relative h-1.5 w-full overflow-hidden rounded-full bg-zinc-200"><ProgressPrimitive.Indicator className="h-full bg-zinc-950 transition-transform duration-500" style={{transform:`translateX(-${100-value}%)`}}/></ProgressPrimitive.Root>}
export function Input(props:React.InputHTMLAttributes<HTMLInputElement>){return <input {...props} className={cn("h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-zinc-900 focus:ring-1 focus:ring-zinc-900",props.className)}/>}
export function Select(props:React.SelectHTMLAttributes<HTMLSelectElement>){return <select {...props} className={cn("h-10 w-full rounded-md border border-zinc-300 bg-white px-3 text-sm outline-none focus:border-zinc-900",props.className)}/>}
