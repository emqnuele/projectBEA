import * as React from "react"

function Badge({ className, variant = "default", ...props }) {
    let baseClasses = "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2";

    let variantClasses = "";
    switch (variant) {
        case "secondary":
            variantClasses = "border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80";
            break;
        case "destructive":
            variantClasses = "border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80";
            break;
        case "outline":
            variantClasses = "text-foreground border-gray-200 text-gray-700";
            break;
        default: // default
            variantClasses = "border-transparent bg-gray-900 text-white hover:bg-gray-800";
            break;
    }

    const combinedClasses = `${baseClasses} ${variantClasses} ${className || ""}`;

    return (
        <div className={combinedClasses} {...props} />
    )
}

export { Badge }
